import os
import re
import io
import json
import uuid
import difflib
import logging
import zipfile
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

import requests
from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument
from starlette.concurrency import run_in_threadpool

AUTH_MODE = os.environ.get("AUTH_MODE", "clerk").strip().lower()
if AUTH_MODE == "selfhost":
    try:
        from backend.self_auth import require_user
    except ModuleNotFoundError:
        from self_auth import require_user
else:
    try:
        from backend.clerk_auth import require_user
    except ModuleNotFoundError:
        from clerk_auth import require_user

logger = logging.getLogger("forja")
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
fernet = Fernet(os.environ["FORJA_ENCRYPTION_KEY"].encode())

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODELS = [
    {"id": "qwen/qwen3-coder-next", "name": "Qwen3 Coder Next (rápido)"},
    {"id": "qwen/qwen3-coder", "name": "Qwen3 Coder (tarefas pesadas)"},
    {"id": "deepseek/deepseek-chat-v3-0324", "name": "DeepSeek V3 (Cirúrgico)"},
]

ROLES = ["admin", "member"]
DEFAULT_ROLE = "member"
RETIRED_ROLES: dict = {}
RANK = {r: len(ROLES) - i for i, r in enumerate(ROLES)}
ENV = "live" if os.environ.get("CLERK_PUBLISHABLE_KEY", "").startswith("pk_live_") else "preview"
IN_ENV = {"env": {"$in": [ENV, None]}}


_buckets: dict = defaultdict(deque)


def rate_limit(key: str, limit: int, window: int):
    t = time.monotonic()
    q = _buckets[key]
    while q and q[0] <= t - window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(status_code=429, detail=f"Muitas requisições. Tente de novo em {int(window - (t - q[0])) + 1}s.")
    q.append(t)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def encrypt(value: str) -> str:
    return fernet.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return fernet.decrypt(value.encode()).decode()


def effective_role(role) -> str:
    role = RETIRED_ROLES.get(role, role)
    return role if role in ROLES else DEFAULT_ROLE


def admin_emails() -> set:
    return {e.strip().lower() for e in os.environ.get("ADMIN_EMAIL", "").split(",") if e.strip()}


SEEDED_MODELS = [{"id": "deepseek/deepseek-chat-v3-0324", "name": "DeepSeek V3 (Cirúrgico)"}]


def _clerk_profile(user_id: str) -> dict:
    admins = admin_emails()
    r = requests.get(f"https://api.clerk.com/v1/users/{user_id}", timeout=10,
                     headers={"Authorization": f"Bearer {os.environ['CLERK_SECRET_KEY']}", "User-Agent": "emergent-app"})
    r.raise_for_status()
    data = r.json()
    emails = data.get("email_addresses", [])
    is_admin = any(e["email_address"].lower() in admins and (e.get("verification") or {}).get("status") == "verified" for e in emails)
    email = emails[0]["email_address"] if emails else ""
    name = " ".join(x for x in [data.get("first_name"), data.get("last_name")] if x) or email
    return {"is_admin": is_admin, "email": email, "name": name}


async def current_member(user: dict = Depends(require_user)) -> dict:
    uid = user["user_id"]
    member = await db.users.find_one({"user_id": uid}, {"_id": 0})
    if member is None or not member.get("role"):
        if AUTH_MODE == "selfhost":
            role, email, name = user.get("role", "admin"), user.get("email", ""), user.get("email", "admin")
        else:
            prof = await run_in_threadpool(_clerk_profile, uid)
            role, email, name = ("admin" if prof["is_admin"] else DEFAULT_ROLE), prof["email"], prof["name"]
        await db.users.update_one({"user_id": uid, "role": {"$in": [None, ""]}}, {"$set": {"role": role}})
        member = await db.users.find_one_and_update(
            {"user_id": uid},
            {"$setOnInsert": {"user_id": uid, "role": role, "email": email, "name": name,
                              "blocked": False, "created_at": now()}},
            upsert=True, projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    elif AUTH_MODE != "selfhost" and member.get("role") != "admin" and (member.get("email") or "").lower() in admin_emails():
        prof = await run_in_threadpool(_clerk_profile, uid)
        if prof["is_admin"]:
            await db.users.update_one({"user_id": uid}, {"$set": {"role": "admin"}})
            member["role"] = "admin"
    if member.get("env") != ENV:
        await db.users.update_one({"user_id": uid}, {"$set": {"env": ENV}})
    return {**member, "env": ENV, "role": effective_role(member["role"])}


def require_role(*roles: str):
    async def check(member: dict = Depends(current_member)) -> dict:
        if member["role"] not in roles:
            raise HTTPException(status_code=403, detail="Not allowed")
        return member
    return check


async def get_settings() -> dict:
    s = await db.settings.find_one({"key": "global"}, {"_id": 0})
    if not s:
        s = {"key": "global", "enabled_models": DEFAULT_MODELS, "default_model": DEFAULT_MODELS[0]["id"],
             "daily_limit_usd": float(os.environ.get("DEFAULT_DAILY_LIMIT_USD", "2"))}
        s["seeded_models"] = [m["id"] for m in SEEDED_MODELS]
        await db.settings.update_one({"key": "global"}, {"$setOnInsert": s}, upsert=True)
    missing = [m for m in SEEDED_MODELS if m["id"] not in s.get("seeded_models", [])]
    if missing:
        ids = {m["id"] for m in s["enabled_models"]}
        s["enabled_models"] = s["enabled_models"] + [m for m in missing if m["id"] not in ids]
        s["seeded_models"] = s.get("seeded_models", []) + [m["id"] for m in missing]
        await db.settings.update_one({"key": "global"}, {"$set": {"enabled_models": s["enabled_models"], "seeded_models": s["seeded_models"]}})
    return s


async def get_project(project_id: str, member: dict) -> dict:
    p = await db.projects.find_one({"id": project_id, "user_id": member["user_id"]}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    return p


def unified_diff(path: str, before: str | None, after: str | None) -> dict:
    a = (before or "").splitlines()
    b = (after or "").splitlines()
    lines = list(difflib.unified_diff(a, b, f"a/{path}", f"b/{path}", lineterm="", n=2))
    added = sum(1 for x in lines if x.startswith("+") and not x.startswith("+++"))
    removed = sum(1 for x in lines if x.startswith("-") and not x.startswith("---"))
    return {"added": added, "removed": removed, "diff": "\n".join(lines[:1500])}


async def record_version(project_id: str, label: str, changes: dict, source: str) -> dict | None:
    """changes: {path: {"before": file_doc|None, "after": file_doc|None}}"""
    if not changes:
        return None
    proj = await db.projects.find_one_and_update({"id": project_id}, {"$inc": {"version_seq": 1}},
                                                 projection={"_id": 0, "version_seq": 1}, return_document=ReturnDocument.AFTER)
    number = proj["version_seq"]
    if number == 1:
        last = await db.versions.find_one({"project_id": project_id}, {"_id": 0, "number": 1}, sort=[("number", -1)])
        if last:
            number = last["number"] + 1
            await db.projects.update_one({"id": project_id}, {"$set": {"version_seq": number}})
    doc = {"id": new_id(), "project_id": project_id, "number": number, "label": label[:140], "source": source,
           "changes": [{"path": p, "before": c["before"], "after": c["after"]} for p, c in changes.items()],
           "created_at": now()}
    await db.versions.insert_one(doc)
    await db.projects.update_one({"id": project_id}, {"$set": {"updated_at": now()}})
    return {"id": doc["id"], "number": doc["number"]}


def file_snapshot(f: dict | None) -> dict | None:
    if not f:
        return None
    return {k: f.get(k) for k in ("kind", "content", "storage_path", "content_type", "size", "summary", "uploaded")}


# ---------- Summaries for uploaded files ----------
def summarize_text(path: str, text: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    n = text.count("\n") + 1
    if ext in ("html", "htm"):
        title = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        tags = re.findall(r"<(header|nav|main|section|article|aside|footer|form)\b([^>]*)>", text, re.I)
        parts = []
        for tag, attrs in tags[:25]:
            m = re.search(r'(?:id|class)="([^"]+)"', attrs)
            parts.append(tag.lower() + (f"#{m.group(1)[:30]}" if m else ""))
        heads = [re.sub(r"<[^>]+>", "", h).strip()[:60] for h in re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", text, re.I | re.S)[:10]]
        return (f"HTML, {n} linhas. Título: {title.group(1).strip()[:80] if title else '—'}. "
                f"Estrutura: {', '.join(parts) or '—'}. Títulos: {' | '.join(heads) or '—'}")
    if ext == "json":
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return f"JSON objeto, {len(text)} bytes, chaves: {', '.join(list(data.keys())[:30])}"
            if isinstance(data, list):
                return f"JSON lista com {len(data)} itens, {len(text)} bytes"
        except Exception:
            pass
        return f"JSON (inválido), {len(text)} bytes"
    if ext in ("js", "jsx", "ts", "tsx", "py", "mjs", "cjs"):
        names = re.findall(r"(?:function\s+(\w+)|class\s+(\w+)|def\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s*)?\()", text)
        flat = [next(x for x in t if x) for t in names][:30]
        return f"Código {ext}, {n} linhas. Funções/classes: {', '.join(flat) or '—'}"
    if ext == "css":
        sels = re.findall(r"^\s*([^{}@/\n][^{}\n]*)\{", text, re.M)[:20]
        return f"CSS, {n} linhas. Seletores: {', '.join(s.strip()[:30] for s in sels)}"
    return f"Texto {ext or ''}, {n} linhas, {len(text)} bytes"


def summarize_image(path: str, data: bytes, content_type: str) -> str:
    dims = ""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            dims = f", {im.width}x{im.height}px"
    except Exception:
        pass
    return f"Imagem {content_type}{dims}, {len(data)//1024} KB. Use pelo caminho '{path}'."


def summarize_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(data))
        title = (r.metadata.title if r.metadata else None) or "—"
        first = re.sub(r"\s+", " ", (r.pages[0].extract_text() or "") if r.pages else "").strip()[:200]
        return f"PDF, {len(r.pages)} páginas, {len(data)//1024} KB. Título: {str(title)[:80]}. Início: {first or '—'}. Leia com read_file (páginas)."
    except Exception:
        return f"PDF, {len(data)//1024} KB (não foi possível ler o texto)."


def summarize_zip(data: bytes) -> str:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        names = [i.filename for i in zf.infolist() if not i.is_dir()]
        total = sum(i.file_size for i in zf.infolist())
        return (f"ZIP com {len(names)} arquivos ({total//1024} KB descompactado). Ex.: {', '.join(names[:15])}"
                f"{' …' if len(names) > 15 else ''}. Use extract_zip para descompactar no projeto.")
    except Exception:
        return f"ZIP inválido, {len(data)//1024} KB."


# ---------- Object storage ----------
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
_storage_key = None


def init_storage(force: bool = False):
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": os.environ["EMERGENT_LLM_KEY"]}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    for attempt in range(2):
        resp = requests.put(f"{STORAGE_URL}/objects/{path}",
                            headers={"X-Storage-Key": init_storage(force=attempt > 0), "Content-Type": content_type},
                            data=data, timeout=120)
        if resp.status_code != 404:
            break
    resp.raise_for_status()
    return resp.json()


def get_object(path: str) -> tuple[bytes, str]:
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage()}, timeout=60)
    if resp.status_code == 404:
        resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage(True)}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp",
               "gif": "image/gif", "ico": "image/x-icon"}
DOC_TYPES = {"pdf": "application/pdf", "zip": "application/zip"}


async def store_binary(user_id: str, path: str, data: bytes, content_type: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower()
    res = await run_in_threadpool(put_object, f"forja/uploads/{user_id}/{new_id()}.{ext}", data, content_type)
    return res["path"]
