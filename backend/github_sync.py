import io
import base64
import hashlib
import zipfile

import httpx
from fastapi import HTTPException

from core import db, now, IMAGE_TYPES, store_binary, get_object
from starlette.concurrency import run_in_threadpool

GH = "https://api.github.com"
EXCLUDED_DIRS = {"node_modules", "build", "dist", ".git", "venv", ".venv", "env", "__pycache__", ".next",
                 "coverage", ".cache", ".pytest_cache", ".mypy_cache", ".idea", ".vscode", "site-packages"}
MAX_FILE = 5 * 1024 * 1024
MAX_TEXT_FILES = 2000
MAX_IMAGES = 300


def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "donas-build-app"}


async def gh(method: str, path: str, token: str, **kw):
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
        r = await c.request(method, f"{GH}{path}", headers=headers(token), **kw)
    if r.status_code >= 400:
        try:
            msg = r.json().get("message", r.text)
        except Exception:
            msg = r.text
        raise HTTPException(status_code=400 if r.status_code != 404 else 404, detail=f"GitHub: {msg[:300]}")
    return r.json() if r.content else {}


def excluded(path: str) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.split("/")[:-1])


async def list_repos(token: str) -> list:
    repos = []
    for page in range(1, 6):
        batch = await gh("GET", f"/user/repos?per_page=100&page={page}&sort=updated&affiliation=owner,collaborator,organization_member", token)
        repos += [{"full_name": r["full_name"], "owner": r["owner"]["login"], "name": r["name"], "private": r["private"],
                   "default_branch": r["default_branch"], "updated_at": r["updated_at"]} for r in batch]
        if len(batch) < 100:
            break
    return repos


async def list_branches(token: str, owner: str, repo: str) -> list:
    data = await gh("GET", f"/repos/{owner}/{repo}/branches?per_page=100", token)
    return [b["name"] for b in data]


MAX_ZIP = 200 * 1024 * 1024


def _clean(path: str):
    parts = [x for x in path.replace("\\", "/").split("/") if x not in ("", ".")]
    return None if ".." in parts or not parts else "/".join(parts)


def _extract(content: bytes, strip_root: bool = True):
    zf = zipfile.ZipFile(io.BytesIO(content))
    texts, images, skipped = [], [], []
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = info.filename.split("/", 1)[1] if strip_root and "/" in info.filename else info.filename
        path = _clean(name)
        if not path or excluded(path):
            continue
        if info.file_size > MAX_FILE:
            skipped.append({"path": path, "reason": "maior que 5 MB"})
            continue
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ext in IMAGE_TYPES:
            if len(images) >= MAX_IMAGES:
                skipped.append({"path": path, "reason": "limite de imagens"})
            else:
                images.append((path, zf.read(info), IMAGE_TYPES[ext]))
            continue
        data = zf.read(info)
        if b"\x00" in data[:8000]:
            skipped.append({"path": path, "reason": "binário"})
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            skipped.append({"path": path, "reason": "binário"})
            continue
        if len(texts) >= MAX_TEXT_FILES:
            skipped.append({"path": path, "reason": "limite de 2.000 arquivos"})
            continue
        texts.append((path, text, len(data)))
    return texts, images, skipped


async def import_repo(token: str, owner: str, repo: str, branch: str, project_id: str, user_id: str) -> dict:
    async with httpx.AsyncClient(timeout=180, follow_redirects=True) as c:
        async with c.stream("GET", f"{GH}/repos/{owner}/{repo}/zipball/{branch}", headers=headers(token)) as r:
            if r.status_code >= 400:
                raise HTTPException(status_code=400, detail=f"GitHub: não foi possível baixar o repositório ({r.status_code}).")
            buf = bytearray()
            async for chunk in r.aiter_bytes():
                buf.extend(chunk)
                if len(buf) > MAX_ZIP:
                    raise HTTPException(status_code=400, detail="Repositório grande demais para importar (mais de 200 MB compactado).")
    texts, images, skipped = await run_in_threadpool(_extract, bytes(buf))
    docs = [{"project_id": project_id, "path": p, "kind": "text", "content": t, "size": n, "updated_at": now()} for p, t, n in texts]
    for path, data, ctype in images:
        sp = await store_binary(user_id, path, data, ctype)
        docs.append({"project_id": project_id, "path": path, "kind": "binary", "storage_path": sp,
                     "content_type": ctype, "size": len(data), "updated_at": now()})
    if docs:
        await db.files.insert_many(docs)
    return {"imported": len(docs), "skipped": skipped}


def git_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


async def push_project(token: str, project: dict, owner: str, repo: str, branch: str, message: str) -> dict:
    ref = await gh("GET", f"/repos/{owner}/{repo}/git/ref/heads/{branch}", token)
    head = ref["object"]["sha"]
    commit = await gh("GET", f"/repos/{owner}/{repo}/git/commits/{head}", token)
    tree = await gh("GET", f"/repos/{owner}/{repo}/git/trees/{commit['tree']['sha']}?recursive=1", token)
    remote = {t["path"]: t["sha"] for t in tree.get("tree", []) if t["type"] == "blob"}
    keep_remote = set(project.get("github", {}).get("skipped_paths") or [])
    entries, local_paths = [], set()
    async for f in db.files.find({"project_id": project["id"]}, {"_id": 0}):
        local_paths.add(f["path"])
        if f["kind"] == "text":
            data = f["content"].encode()
            if remote.get(f["path"]) == git_sha(data):
                continue
            entries.append({"path": f["path"], "mode": "100644", "type": "blob", "content": f["content"]})
        else:
            data, _ = await run_in_threadpool(get_object, f["storage_path"])
            if remote.get(f["path"]) == git_sha(data):
                continue
            blob = await gh("POST", f"/repos/{owner}/{repo}/git/blobs", token,
                            json={"content": base64.b64encode(data).decode(), "encoding": "base64"})
            entries.append({"path": f["path"], "mode": "100644", "type": "blob", "sha": blob["sha"]})
    for path in remote:
        if path not in local_paths and path not in keep_remote and not excluded(path) and path != ".gitkeep":
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
    if not entries:
        return {"changed": 0, "commit": head, "message": "Nada para enviar — o GitHub já está igual."}
    new_tree = await gh("POST", f"/repos/{owner}/{repo}/git/trees", token, json={"base_tree": commit["tree"]["sha"], "tree": entries})
    new_commit = await gh("POST", f"/repos/{owner}/{repo}/git/commits", token,
                          json={"message": message, "tree": new_tree["sha"], "parents": [head]})
    await gh("PATCH", f"/repos/{owner}/{repo}/git/refs/heads/{branch}", token, json={"sha": new_commit["sha"]})
    return {"changed": len(entries), "commit": new_commit["sha"], "url": new_commit.get("html_url")}
