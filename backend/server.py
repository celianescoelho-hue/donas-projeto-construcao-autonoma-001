import io
import os
import re
import json
import asyncio
import logging
import zipfile
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import httpx
from fastapi import FastAPI, APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING, IndexModel
from starlette.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

try:
    from backend.clerk_auth import clerk_router
except ModuleNotFoundError:
    from clerk_auth import clerk_router

from core import (db, client, now, new_id, encrypt, decrypt, current_member, require_role, get_settings, get_project,
                  record_version, file_snapshot, rate_limit, summarize_text, summarize_image, store_binary, get_object, init_storage,
                  effective_role, ROLES, RANK, IN_ENV, RETIRED_ROLES, IMAGE_TYPES, OPENROUTER_BASE, logger)
from agent import Agent, resolve_key, clean_path
import github_sync as ghs

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

INDEXES = {
    "users": [IndexModel([("user_id", ASCENDING)], name="user_id", unique=True)],
    "projects": [IndexModel([("id", ASCENDING)], name="id", unique=True),
                 IndexModel([("user_id", ASCENDING), ("updated_at", DESCENDING)], name="user_updated")],
    "files": [IndexModel([("project_id", ASCENDING), ("path", ASCENDING)], name="project_path", unique=True)],
    "messages": [IndexModel([("project_id", ASCENDING), ("created_at", ASCENDING)], name="project_created")],
    "versions": [IndexModel([("project_id", ASCENDING), ("number", DESCENDING)], name="project_number_unique", unique=True),
                 IndexModel([("id", ASCENDING)], name="id", unique=True)],
    "usage": [IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_created"),
              IndexModel([("created_at", DESCENDING)], name="created_desc")],
    "settings": [IndexModel([("key", ASCENDING)], name="key", unique=True)],
}


async def ensure_indexes():
    for col, models in INDEXES.items():
        for m in models:
            try:
                await db[col].create_indexes([m])
            except Exception as exc:
                logger.error("ensure_indexes(%s): %s", col, exc)


app = FastAPI()


@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return Response(content=json.dumps({"detail": str(exc) or "Valor inválido"}), status_code=400, media_type="application/json")
api = APIRouter(prefix="/api")


async def active_member(member: dict = Depends(current_member)) -> dict:
    if member.get("blocked"):
        raise HTTPException(status_code=403, detail="Sua conta está bloqueada. Fale com o administrador.")
    return member


# ---------------- Me & settings ----------------
@api.get("/me")
async def me(member: dict = Depends(current_member)):
    full = await db.users.find_one({"user_id": member["user_id"]}, {"_id": 0})
    s = await get_settings()
    return {"user_id": member["user_id"], "email": full.get("email"), "name": full.get("name"), "role": member["role"],
            "blocked": bool(full.get("blocked")), "has_openrouter_key": bool(full.get("openrouter_key_enc")),
            "github_login": full.get("github_login"), "daily_limit_usd": s["daily_limit_usd"],
            "platform_key_available": bool(os.environ.get("OPENROUTER_API_KEY"))}


class KeyIn(BaseModel):
    key: str = Field(min_length=10, max_length=300)


@api.put("/settings/openrouter-key")
async def set_or_key(body: KeyIn, member: dict = Depends(current_member)):
    rate_limit(f"key:{member['user_id']}", 5, 60)
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{OPENROUTER_BASE}/key", headers={"Authorization": f"Bearer {body.key.strip()}"})
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail="Chave OpenRouter inválida.")
    await db.users.update_one({"user_id": member["user_id"]}, {"$set": {"openrouter_key_enc": encrypt(body.key.strip())}})
    return {"ok": True}


@api.delete("/settings/openrouter-key")
async def del_or_key(member: dict = Depends(current_member)):
    await db.users.update_one({"user_id": member["user_id"]}, {"$unset": {"openrouter_key_enc": ""}})
    return {"ok": True}


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=300)


@api.put("/settings/github")
async def set_github(body: TokenIn, member: dict = Depends(current_member)):
    rate_limit(f"ghkey:{member['user_id']}", 5, 60)
    user = await ghs.gh("GET", "/user", body.token.strip())
    await db.users.update_one({"user_id": member["user_id"]},
                              {"$set": {"github_token_enc": encrypt(body.token.strip()), "github_login": user["login"]}})
    return {"ok": True, "login": user["login"]}


@api.delete("/settings/github")
async def del_github(member: dict = Depends(current_member)):
    await db.users.update_one({"user_id": member["user_id"]}, {"$unset": {"github_token_enc": "", "github_login": ""}})
    return {"ok": True}


async def github_token(member: dict) -> str:
    full = await db.users.find_one({"user_id": member["user_id"]}, {"_id": 0, "github_token_enc": 1})
    if not full or not full.get("github_token_enc"):
        raise HTTPException(status_code=400, detail="Conecte o GitHub em Configurações primeiro.")
    return decrypt(full["github_token_enc"])


@api.get("/models")
async def models(member: dict = Depends(current_member)):
    s = await get_settings()
    return {"models": s["enabled_models"], "default_model": s["default_model"]}


# ---------------- Projects ----------------
class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ProjectPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    model: Optional[str] = None


def project_doc(member, name, extra=None):
    return {"id": new_id(), "user_id": member["user_id"], "name": name, "model": None, "github": None,
            "created_at": now(), "updated_at": now(), **(extra or {})}


@api.get("/projects")
async def list_projects(member: dict = Depends(current_member)):
    items = await db.projects.find({"user_id": member["user_id"]}, {"_id": 0}).sort("updated_at", -1).to_list(500)
    for p in items:
        p["file_count"] = await db.files.count_documents({"project_id": p["id"]})
        if p.get("github"):
            p["github"] = {k: v for k, v in p["github"].items() if k != "skipped_paths"}
    return items


@api.post("/projects")
async def create_project(body: ProjectIn, member: dict = Depends(active_member)):
    rate_limit(f"newproj:{member['user_id']}", 20, 3600)
    doc = project_doc(member, body.name.strip())
    await db.projects.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.patch("/projects/{pid}")
async def patch_project(pid: str, body: ProjectPatch, member: dict = Depends(current_member)):
    await get_project(pid, member)
    upd = {}
    if body.name:
        upd["name"] = body.name.strip()
    if body.model is not None:
        s = await get_settings()
        if body.model not in [m["id"] for m in s["enabled_models"]]:
            raise HTTPException(status_code=400, detail="Modelo não liberado.")
        upd["model"] = body.model
    if upd:
        await db.projects.update_one({"id": pid}, {"$set": upd})
    return await get_project(pid, member)


@api.delete("/projects/{pid}")
async def delete_project(pid: str, member: dict = Depends(current_member)):
    await get_project(pid, member)
    for col in ("files", "messages", "versions"):
        await db[col].delete_many({"project_id": pid})
    await db.projects.delete_one({"id": pid, "user_id": member["user_id"]})
    return {"ok": True}


def public_file(f):
    return {"path": f["path"], "kind": f["kind"], "content": f.get("content") if f["kind"] == "text" else None,
            "content_type": f.get("content_type"), "size": f.get("size", 0), "uploaded": f.get("uploaded", False),
            "summary": f.get("summary")}


@api.get("/projects/{pid}")
async def get_project_full(pid: str, member: dict = Depends(current_member)):
    p = await get_project(pid, member)
    files = await db.files.find({"project_id": pid}, {"_id": 0}).sort("path", 1).to_list(5000)
    if p.get("github"):
        p["github"] = {k: v for k, v in p["github"].items() if k != "skipped_paths"}
    return {"project": p, "files": [public_file(f) for f in files]}


class FileIn(BaseModel):
    path: str
    content: str


@api.put("/projects/{pid}/files")
async def save_file(pid: str, body: FileIn, member: dict = Depends(current_member)):
    await get_project(pid, member)
    path = clean_path(body.path)
    if not path:
        raise HTTPException(status_code=400, detail="Caminho inválido")
    before = await db.files.find_one({"project_id": pid, "path": path}, {"_id": 0})
    if before and before["kind"] != "text":
        raise HTTPException(status_code=400, detail="Arquivo binário não pode ser editado.")
    if before and before.get("content") == body.content:
        return {"ok": True, "unchanged": True}
    doc = {"project_id": pid, "path": path, "kind": "text", "content": body.content, "size": len(body.content.encode()),
           "uploaded": (before or {}).get("uploaded", False), "summary": (before or {}).get("summary"), "updated_at": now()}
    await db.files.update_one({"project_id": pid, "path": path}, {"$set": doc}, upsert=True)
    await record_version(pid, f"Edição manual: {path}", {path: {"before": file_snapshot(before), "after": file_snapshot(doc)}}, "manual")
    return {"ok": True}


@api.delete("/projects/{pid}/files")
async def delete_file(pid: str, path: str = Query(...), member: dict = Depends(current_member)):
    await get_project(pid, member)
    path = clean_path(path)
    before = await db.files.find_one({"project_id": pid, "path": path}, {"_id": 0})
    if not before:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    await db.files.delete_one({"project_id": pid, "path": path})
    await record_version(pid, f"Arquivo apagado: {path}", {path: {"before": file_snapshot(before), "after": None}}, "manual")
    return {"ok": True}


TEXT_UPLOAD = {"html", "htm", "css", "js", "jsx", "ts", "tsx", "json", "md", "txt", "py", "svg"}
MAX_UPLOAD = 10 * 1024 * 1024


@api.post("/projects/{pid}/upload")
async def upload(pid: str, files: List[UploadFile] = File(...), directory: str = Form(""), member: dict = Depends(active_member)):
    rate_limit(f"upload:{member['user_id']}", 20, 60)
    await get_project(pid, member)
    base = clean_path(directory)
    saved, changes, errors = [], {}, []
    for up in files:
        name = clean_path(up.filename.split("/")[-1])
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        data = await up.read()
        if len(data) > MAX_UPLOAD:
            errors.append(f"{name}: maior que 10 MB")
            continue
        path = f"{base}/{name}" if base else name
        before = await db.files.find_one({"project_id": pid, "path": path}, {"_id": 0})
        if ext in TEXT_UPLOAD:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                errors.append(f"{name}: não é texto UTF-8")
                continue
            summary = summarize_text(path, text) if ext != "svg" else f"Imagem SVG, {len(data)//1024} KB. Use pelo caminho '{path}'."
            doc = {"project_id": pid, "path": path, "kind": "text", "content": text, "size": len(data),
                   "uploaded": True, "summary": summary, "updated_at": now()}
        elif ext in IMAGE_TYPES:
            sp = await store_binary(member["user_id"], path, data, IMAGE_TYPES[ext])
            doc = {"project_id": pid, "path": path, "kind": "binary", "storage_path": sp, "content_type": IMAGE_TYPES[ext],
                   "size": len(data), "uploaded": True, "summary": summarize_image(path, data, IMAGE_TYPES[ext]), "updated_at": now()}
        else:
            errors.append(f"{name}: tipo não suportado")
            continue
        await db.files.update_one({"project_id": pid, "path": path}, {"$set": doc}, upsert=True)
        changes[path] = {"before": file_snapshot(before), "after": file_snapshot(doc)}
        saved.append(public_file(doc))
    await record_version(pid, f"Upload: {', '.join(list(changes)[:5])}", changes, "upload")
    return {"saved": saved, "errors": errors}


@api.get("/projects/{pid}/asset")
async def asset(pid: str, path: str = Query(...), member: dict = Depends(current_member)):
    await get_project(pid, member)
    f = await db.files.find_one({"project_id": pid, "path": clean_path(path)}, {"_id": 0})
    if not f or f["kind"] != "binary":
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    data, _ = await run_in_threadpool(get_object, f["storage_path"])
    return Response(content=data, media_type=f.get("content_type") or "application/octet-stream")


@api.get("/projects/{pid}/zip")
async def download_zip(pid: str, member: dict = Depends(current_member)):
    p = await get_project(pid, member)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        async for f in db.files.find({"project_id": pid}, {"_id": 0}):
            if f["kind"] == "text":
                zf.writestr(f["path"], f["content"])
            else:
                data, _ = await run_in_threadpool(get_object, f["storage_path"])
                zf.writestr(f["path"], data)
    name = re.sub(r"[^a-zA-Z0-9_-]+", "-", p["name"]).strip("-") or "projeto"
    return Response(content=buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}.zip"'})


# ---------------- Chat ----------------
@api.get("/projects/{pid}/messages")
async def messages(pid: str, member: dict = Depends(current_member)):
    await get_project(pid, member)
    return await db.messages.find({"project_id": pid}, {"_id": 0}).sort("created_at", 1).to_list(500)


class ChatIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=30000)
    model: Optional[str] = None


RUNNING: dict = {}


@api.post("/projects/{pid}/chat")
async def chat(pid: str, body: ChatIn, member: dict = Depends(active_member)):
    project = await get_project(pid, member)
    if RUNNING.get(pid):
        raise HTTPException(status_code=409, detail="A IA já está trabalhando neste projeto.")
    if sum(1 for u in RUNNING.values() if u == member["user_id"]) >= 2:
        raise HTTPException(status_code=429, detail="Você já tem 2 tarefas da IA em andamento. Aguarde uma terminar.")
    rate_limit(f"chat:{member['user_id']}", 8, 60)
    rate_limit(f"chat_h:{member['user_id']}", 80, 3600)
    RUNNING[pid] = member["user_id"]
    try:
        return await _start_chat(pid, project, body, member)
    except BaseException:
        RUNNING.pop(pid, None)
        raise


async def _start_chat(pid: str, project: dict, body: ChatIn, member: dict):
    s = await get_settings()
    allowed = [m["id"] for m in s["enabled_models"]]
    model = body.model or project.get("model") or s["default_model"]
    if model not in allowed:
        model = s["default_model"]
    try:
        api_key, source = await resolve_key(member)
    except ValueError as e:
        raise HTTPException(status_code=402, detail=str(e))
    await db.messages.insert_one({"id": new_id(), "project_id": pid, "role": "user", "content": body.prompt,
                                  "model": model, "created_at": now()})
    if project.get("model") != model:
        await db.projects.update_one({"id": pid}, {"$set": {"model": model}})
    queue: asyncio.Queue = asyncio.Queue()
    agent = Agent(project, member, queue)

    async def runner():
        try:
            await agent.run(body.prompt, model, api_key, source)
        finally:
            RUNNING.pop(pid, None)

    asyncio.create_task(runner())

    async def events():
        yield f"data: {json.dumps({'type': 'start', 'model': model, 'key_source': source})}\n\n"
        while True:
            try:
                ev = await asyncio.wait_for(queue.get(), timeout=15)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue
            if ev is None:
                break
            yield f"data: {json.dumps(ev, default=str)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------- Versions ----------------
@api.get("/projects/{pid}/versions")
async def versions(pid: str, member: dict = Depends(current_member)):
    await get_project(pid, member)
    items = await db.versions.find({"project_id": pid}, {"_id": 0}).sort("number", -1).to_list(300)
    return [{"id": v["id"], "number": v["number"], "label": v["label"], "source": v["source"], "created_at": v["created_at"],
             "paths": [c["path"] for c in v["changes"]][:30], "count": len(v["changes"])} for v in items]


async def apply_snapshot(pid: str, path: str, snap: dict | None):
    if snap is None:
        await db.files.delete_one({"project_id": pid, "path": path})
    else:
        await db.files.update_one({"project_id": pid, "path": path},
                                  {"$set": {**snap, "project_id": pid, "path": path, "updated_at": now()}}, upsert=True)


@api.post("/projects/{pid}/versions/{vid}/restore")
async def restore(pid: str, vid: str, member: dict = Depends(current_member)):
    await get_project(pid, member)
    target = await db.versions.find_one({"id": vid, "project_id": pid}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Versão não encontrada")
    newer = await db.versions.find({"project_id": pid, "number": {"$gt": target["number"]}}, {"_id": 0}).sort("number", -1).to_list(1000)
    paths = {c["path"] for v in newer for c in v["changes"]}
    current = {p: file_snapshot(await db.files.find_one({"project_id": pid, "path": p}, {"_id": 0})) for p in paths}
    for v in newer:
        for c in v["changes"]:
            await apply_snapshot(pid, c["path"], c["before"])
    final = {p: file_snapshot(await db.files.find_one({"project_id": pid, "path": p}, {"_id": 0})) for p in paths}
    changes = {p: {"before": current[p], "after": final[p]} for p in paths if current[p] != final[p]}
    await record_version(pid, f"Restaurado para a versão {target['number']}", changes, "restore")
    return {"ok": True, "changed": len(changes)}


# ---------------- GitHub ----------------
@api.get("/github/repos")
async def gh_repos(member: dict = Depends(current_member)):
    rate_limit(f"repos:{member['user_id']}", 20, 60)
    return await ghs.list_repos(await github_token(member))


@api.get("/github/branches")
async def gh_branches(owner: str, repo: str, member: dict = Depends(current_member)):
    return await ghs.list_branches(await github_token(member), owner, repo)


class ImportIn(BaseModel):
    owner: str
    repo: str
    branch: str
    name: Optional[str] = None


async def populate_from_github(pid: str, body: ImportIn, member: dict, token: str) -> dict:
    res = await ghs.import_repo(token, body.owner, body.repo, body.branch, pid, member["user_id"])
    await db.projects.update_one({"id": pid}, {"$set": {"github": {"owner": body.owner, "repo": body.repo, "branch": body.branch,
                                  "imported_at": now(), "skipped_paths": [s["path"] for s in res["skipped"]]}, "updated_at": now()}})
    await db.messages.insert_one({"id": new_id(), "project_id": pid, "role": "assistant", "created_at": now(),
        "content": f"Repositório {body.owner}/{body.repo} ({body.branch}) importado: {res['imported']} arquivos." +
                   (f" {len(res['skipped'])} ficaram de fora (pastas geradas, binários ou acima de 5 MB)." if res["skipped"] else "") +
                   " Diga o que você quer continuar construindo.", "changes": []})
    return {"project_id": pid, "imported": res["imported"], "skipped": res["skipped"][:200], "skipped_count": len(res["skipped"])}


@api.post("/projects/import")
async def import_project(body: ImportIn, member: dict = Depends(active_member)):
    rate_limit(f"import:{member['user_id']}", 5, 600)
    token = await github_token(member)
    doc = project_doc(member, (body.name or body.repo).strip()[:80])
    await db.projects.insert_one(doc)
    try:
        return await populate_from_github(doc["id"], body, member, token)
    except Exception:
        await db.files.delete_many({"project_id": doc["id"]})
        await db.projects.delete_one({"id": doc["id"]})
        raise


@api.post("/projects/{pid}/github/import")
async def import_into_project(pid: str, body: ImportIn, member: dict = Depends(active_member)):
    rate_limit(f"import:{member['user_id']}", 5, 600)
    await get_project(pid, member)
    if RUNNING.get(pid):
        raise HTTPException(status_code=409, detail="Este projeto está ocupado (IA ou importação em andamento).")
    RUNNING[pid] = member["user_id"]
    try:
        if await db.files.count_documents({"project_id": pid}) > 0:
            raise HTTPException(status_code=409, detail="Este projeto já tem arquivos. Crie um projeto novo para importar um repositório.")
        token = await github_token(member)
        try:
            return await populate_from_github(pid, body, member, token)
        except Exception:
            await db.files.delete_many({"project_id": pid})
            raise
    finally:
        RUNNING.pop(pid, None)


@api.get("/projects/{pid}/github/suggest-message")
async def suggest_message(pid: str, member: dict = Depends(current_member)):
    p = await get_project(pid, member)
    since = (p.get("github") or {}).get("last_pushed_at") or (p.get("github") or {}).get("imported_at") or ""
    vs = await db.versions.find({"project_id": pid, "created_at": {"$gt": since}}, {"_id": 0, "label": 1, "changes.path": 1}).sort("number", 1).to_list(50)
    if not vs:
        return {"message": "Atualização via Donas Build apps with ai"}
    files = sorted({c["path"] for v in vs for c in v["changes"]})
    title = vs[-1]["label"].split("\n")[0][:60] if len(vs) == 1 else f"Donas: {len(vs)} alterações em {len(files)} arquivos"
    body = "\n".join(f"- {v['label'].splitlines()[0][:90]}" for v in vs[-10:])
    return {"message": f"{title}\n\n{body}"}


class PushIn(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    new_repo_name: Optional[str] = None
    private: bool = True


@api.post("/projects/{pid}/github/push")
async def push(pid: str, body: PushIn, member: dict = Depends(active_member)):
    rate_limit(f"push:{member['user_id']}", 6, 60)
    p = await get_project(pid, member)
    token = await github_token(member)
    gh = p.get("github")
    if body.new_repo_name:
        name = re.sub(r"[^a-zA-Z0-9._-]+", "-", body.new_repo_name.strip())
        repo = await ghs.gh("POST", "/user/repos", token, json={"name": name, "private": body.private, "auto_init": True})
        gh = {"owner": repo["owner"]["login"], "repo": repo["name"], "branch": repo["default_branch"] or "main", "skipped_paths": []}
        await asyncio.sleep(2)
    if not gh:
        raise HTTPException(status_code=400, detail="Informe o nome de um repositório novo.")
    res = await ghs.push_project(token, {**p, "github": gh}, gh["owner"], gh["repo"], gh["branch"], body.message)
    await db.projects.update_one({"id": pid}, {"$set": {"github.owner": gh["owner"], "github.repo": gh["repo"], "github.branch": gh["branch"],
                                                        "github.last_pushed_at": now()}} if p.get("github") else
                                 {"$set": {"github": {**gh, "last_pushed_at": now()}}})
    return {**res, "repo": f"{gh['owner']}/{gh['repo']}", "branch": gh["branch"]}


# ---------------- Admin ----------------
@api.get("/admin/overview")
async def admin_overview(admin: dict = Depends(require_role("admin"))):
    agg = await db.usage.aggregate([{"$group": {"_id": "$key_source", "cost": {"$sum": "$cost"},
                                                "tokens": {"$sum": {"$ifNull": ["$total_tokens", 0]}}, "calls": {"$sum": 1}}}]).to_list(10)
    by = {a["_id"]: a for a in agg}
    return {"users": await db.users.count_documents(IN_ENV), "projects": await db.projects.count_documents({}),
            "messages": await db.messages.count_documents({"role": "user"}),
            "cost_platform": by.get("platform", {}).get("cost", 0), "cost_user": by.get("user", {}).get("cost", 0),
            "tokens": sum(a["tokens"] for a in agg), "calls": sum(a["calls"] for a in agg)}


@api.get("/users")
async def list_users(admin: dict = Depends(require_role("admin"))):
    people = await db.users.find(IN_ENV, {"_id": 0}).to_list(1000)
    spend = {a["_id"]: a for a in await db.usage.aggregate([{"$group": {"_id": "$user_id", "cost": {"$sum": "$cost"}, "calls": {"$sum": 1}}}]).to_list(2000)}
    out = []
    for p in people:
        out.append({"user_id": p["user_id"], "email": p.get("email"), "name": p.get("name"), "role": effective_role(p.get("role")),
                    "blocked": bool(p.get("blocked")), "own_key": bool(p.get("openrouter_key_enc")),
                    "github_login": p.get("github_login"), "created_at": p.get("created_at"),
                    "cost": spend.get(p["user_id"], {}).get("cost", 0), "calls": spend.get(p["user_id"], {}).get("calls", 0),
                    "projects": await db.projects.count_documents({"user_id": p["user_id"]})})
    return {"roles": [r for r in ROLES if RANK[r] <= RANK[admin["role"]]], "users": out}


class RoleIn(BaseModel):
    role: str


@api.patch("/users/{user_id}/role")
async def set_role(user_id: str, body: RoleIn, admin: dict = Depends(require_role("admin"))):
    if body.role not in ROLES or RANK[body.role] > RANK[admin["role"]]:
        raise HTTPException(status_code=403, detail="Not allowed")
    target = await db.users.find_one({"user_id": user_id, **IN_ENV}, {"_id": 0})
    if target is None:
        raise HTTPException(status_code=404, detail="Not found")
    if (effective_role(target.get("role")) == "admin" and body.role != "admin"
            and await db.users.count_documents({"role": "admin", **IN_ENV}) <= 1):
        raise HTTPException(status_code=409, detail="Mantenha pelo menos um admin")
    await db.users.update_one({"user_id": user_id}, {"$set": {"role": body.role}})
    return {"user_id": user_id, "role": body.role}


class BlockIn(BaseModel):
    blocked: bool


@api.patch("/admin/users/{user_id}/block")
async def block_user(user_id: str, body: BlockIn, admin: dict = Depends(require_role("admin"))):
    if user_id == admin["user_id"]:
        raise HTTPException(status_code=400, detail="Você não pode bloquear a si mesmo.")
    res = await db.users.update_one({"user_id": user_id, **IN_ENV}, {"$set": {"blocked": body.blocked}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"user_id": user_id, "blocked": body.blocked}


@api.get("/admin/settings")
async def admin_settings(admin: dict = Depends(require_role("admin"))):
    s = await get_settings()
    return {**s, "platform_key_available": bool(os.environ.get("OPENROUTER_API_KEY"))}


class ModelItem(BaseModel):
    id: str
    name: str


class SettingsIn(BaseModel):
    enabled_models: Optional[List[ModelItem]] = None
    default_model: Optional[str] = None
    daily_limit_usd: Optional[float] = Field(default=None, ge=0, le=10000)


@api.put("/admin/settings")
async def update_settings(body: SettingsIn, admin: dict = Depends(require_role("admin"))):
    s = await get_settings()
    enabled = [m.model_dump() for m in body.enabled_models] if body.enabled_models is not None else s["enabled_models"]
    if not enabled:
        raise HTTPException(status_code=400, detail="Libere pelo menos um modelo.")
    default = body.default_model or s["default_model"]
    if default not in [m["id"] for m in enabled]:
        default = enabled[0]["id"]
    upd = {"enabled_models": enabled, "default_model": default}
    if body.daily_limit_usd is not None:
        upd["daily_limit_usd"] = body.daily_limit_usd
    await db.settings.update_one({"key": "global"}, {"$set": upd})
    return {**await get_settings(), "platform_key_available": bool(os.environ.get("OPENROUTER_API_KEY"))}


@api.get("/admin/openrouter-models")
async def openrouter_models(admin: dict = Depends(require_role("admin"))):
    rate_limit(f"ormodels:{admin['user_id']}", 10, 60)
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{OPENROUTER_BASE}/models")
    if r.is_error:
        raise HTTPException(status_code=502, detail="Não foi possível listar os modelos da OpenRouter.")
    out = []
    for m in r.json().get("data", []):
        if "tools" not in (m.get("supported_parameters") or []):
            continue
        pr = m.get("pricing") or {}
        out.append({"id": m["id"], "name": m.get("name") or m["id"], "context_length": m.get("context_length"),
                    "prompt_price": pr.get("prompt"), "completion_price": pr.get("completion")})
    return sorted(out, key=lambda x: x["id"])


@api.get("/admin/usage")
async def admin_usage(limit: int = Query(100, ge=1, le=500), admin: dict = Depends(require_role("admin"))):
    rows = await db.usage.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    emails = {u["user_id"]: u.get("email") for u in await db.users.find({}, {"_id": 0, "user_id": 1, "email": 1}).to_list(2000)}
    for r in rows:
        r["email"] = emails.get(r["user_id"])
    return rows


@app.middleware("http")
async def security_middleware(request, call_next):
    path = request.url.path
    if path.startswith("/api/") and not path.startswith("/api/__clerk"):
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()
        try:
            rate_limit(f"ip:{ip}", 600, 60)
        except HTTPException as e:
            return Response(content=json.dumps({"detail": e.detail}), status_code=429, media_type="application/json")
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


app.include_router(api)
app.include_router(clerk_router)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def startup():
    app.state.index_task = asyncio.create_task(ensure_indexes())
    for old, new in RETIRED_ROLES.items():
        await db.users.update_many({"role": old}, {"$set": {"role": new}})
    try:
        await run_in_threadpool(init_storage)
    except Exception as e:
        logger.error("Storage init failed: %s", e)


@app.on_event("shutdown")
async def shutdown():
    app.state.index_task.cancel()
    client.close()
