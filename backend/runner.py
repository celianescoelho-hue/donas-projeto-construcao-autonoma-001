"""Full-stack preview runner.

Runs a project's real Python FastAPI backend (uvicorn on a free port) against a
local MongoDB with a dedicated DB_NAME=preview_{pid}. The React front-end keeps
being rendered by the instant in-browser bundler; its /api calls are proxied to
this real backend. Processes are reaped after 30 min idle and restarted whenever
the files under backend/ change.
"""
import os
import sys
import signal
import socket
import shutil
import secrets
import hashlib
import logging
import threading
import subprocess
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

import core

logger = logging.getLogger("forja.runner")

WORK_ROOT = os.environ.get("PREVIEW_DIR", "/tmp/donas_previews")
IDLE_SECONDS = 30 * 60
BASE_DEPS = ["fastapi", "uvicorn[standard]", "motor", "pydantic", "python-dotenv"]
SKIP_DIRS = {"node_modules", "build", "dist", ".git", "__pycache__", ".venv", "venv", "env"}
MAX_WAIT = 40  # seconds to wait for uvicorn to bind

# pid -> state dict
RUNNERS: dict = {}
_locks: dict = {}

# Dedicated, isolated MongoDB for previews. Generated backends connect ONLY to
# this instance (never the platform DB), so user/AI code cannot read the main
# database or the encrypted secrets stored there.
_MONGO: dict = {}
_mongo_lock = threading.Lock()


def preview_mongo_url() -> str:
    with _mongo_lock:
        proc = _MONGO.get("proc")
        if proc and proc.poll() is None:
            return _MONGO["url"]
        port = _free_port()
        dbpath = os.path.join(WORK_ROOT, "_mongo")
        os.makedirs(dbpath, exist_ok=True)
        p = subprocess.Popen(
            ["mongod", "--dbpath", dbpath, "--port", str(port), "--bind_ip", "127.0.0.1",
             "--wiredTigerCacheSizeGB", "0.25", "--quiet"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        import time
        waited = 0.0
        while waited < 20 and not _port_open(port):
            if p.poll() is not None:
                raise RuntimeError("Não foi possível iniciar o MongoDB da prévia.")
            time.sleep(0.4)
            waited += 0.4
        _MONGO.update(proc=p, url=f"mongodb://127.0.0.1:{port}", port=port)
        return _MONGO["url"]


def _now() -> float:
    import time
    return time.monotonic()


def work_dir(pid: str) -> str:
    return os.path.join(WORK_ROOT, pid)


def _lock(pid: str) -> threading.Lock:
    return _locks.setdefault(pid, threading.Lock())


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


async def sync_files(pid: str) -> tuple[bool, str]:
    """Write the project's files to disk (preserving .venv). Returns (has_backend, signature)."""
    root = work_dir(pid)
    if os.path.isdir(root):
        for name in os.listdir(root):
            if name == ".venv":
                continue
            p = os.path.join(root, name)
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)
    else:
        os.makedirs(root, exist_ok=True)
    files = await core.db.files.find({"project_id": pid}, {"_id": 0}).sort("path", 1).to_list(5000)
    has_backend = False
    sig = hashlib.sha256()
    for f in files:
        path = f["path"]
        if any(part in SKIP_DIRS for part in path.split("/")):
            continue
        dest = os.path.join(root, path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if f["kind"] == "text":
            data = (f.get("content") or "").encode()
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(f.get("content") or "")
        else:
            if not f.get("storage_path"):
                continue
            try:
                data, _ = await run_in_threadpool(core.get_object, f["storage_path"])
            except Exception:
                continue
            with open(dest, "wb") as fh:
                fh.write(data)
        if path == "backend/server.py":
            has_backend = True
        if path.startswith("backend/"):
            sig.update(path.encode())
            sig.update(data)
    return has_backend, sig.hexdigest()


def _install_and_launch(pid: str, env_vars: dict):
    """Blocking install + uvicorn launch, run in a background thread."""
    st = RUNNERS[pid]
    root = work_dir(pid)
    backend_dir = os.path.join(root, "backend")
    venv = os.path.join(root, ".venv")
    pybin = os.path.join(venv, "bin", "python")
    pipbin = os.path.join(venv, "bin", "pip")
    log: list[str] = []
    try:
        st["status"] = "installing"
        if not os.path.exists(pybin):
            log.append("$ criando ambiente virtual…")
            subprocess.run([sys.executable, "-m", "venv", venv], check=True, capture_output=True, text=True, timeout=120)
        req = os.path.join(backend_dir, "requirements.txt")
        cmd = [pipbin, "install", "-q"]
        cmd += ["-r", req] if os.path.exists(req) else BASE_DEPS
        log.append("$ pip install " + ("-r requirements.txt" if os.path.exists(req) else " ".join(BASE_DEPS)))
        r = subprocess.run(cmd, cwd=backend_dir, capture_output=True, text=True, timeout=600)
        log.append((r.stdout or "")[-1500:])
        if r.returncode != 0:
            log.append("ERRO pip:\n" + (r.stderr or "")[-2000:])
            st.update(status="error", log="\n".join(log))
            return
        # ensure uvicorn is present even if requirements.txt forgot it
        subprocess.run([pipbin, "install", "-q", "uvicorn[standard]", "motor"], cwd=backend_dir,
                       capture_output=True, text=True, timeout=300)

        port = _free_port()
        # Minimal, isolated environment: NO platform secrets, NO platform MONGO_URL.
        # Only the project's own env vars plus a dedicated preview Mongo instance.
        proc_env = {
            "PATH": f"{venv}/bin:" + os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
            "VIRTUAL_ENV": venv,
            "PYTHONUNBUFFERED": "1",
        }
        for k, v in (env_vars or {}).items():
            if k not in ("MONGO_URL", "DB_NAME", "PORT") and isinstance(v, str):
                proc_env[k] = v
        try:
            proc_env["MONGO_URL"] = preview_mongo_url()
        except Exception as e:
            log.append(f"Aviso: Mongo da prévia indisponível ({e}).")
        proc_env["DB_NAME"] = f"preview_{pid}"
        proc_env["PORT"] = str(port)
        log.append(f"$ uvicorn server:app --port {port}  (DB_NAME=preview_{pid})")
        proc = subprocess.Popen(
            [os.path.join(venv, "bin", "uvicorn"), "server:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=backend_dir, env=proc_env, start_new_session=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        st.update(proc=proc, port=port)

        import time
        waited = 0.0
        while waited < MAX_WAIT:
            if proc.poll() is not None:
                out = (proc.stdout.read() if proc.stdout else "") or ""
                log.append("O backend encerrou ao iniciar:\n" + out[-2000:])
                st.update(status="error", log="\n".join(log))
                return
            if _port_open(port):
                log.append(f"✓ backend rodando na porta {port}")
                st.update(status="running", log="\n".join(log), last_active=_now())
                threading.Thread(target=_drain_logs, args=(pid, proc), daemon=True).start()
                return
            time.sleep(0.5)
            waited += 0.5
        log.append("Tempo esgotado esperando o backend responder.")
        st.update(status="error", log="\n".join(log))
        _kill_proc(proc)
    except subprocess.TimeoutExpired:
        log.append("Tempo esgotado durante a instalação das dependências.")
        st.update(status="error", log="\n".join(log))
    except Exception as e:  # noqa
        log.append(f"Falha ao iniciar: {e}")
        st.update(status="error", log="\n".join(log))


def _drain_logs(pid: str, proc):
    buf: list[str] = []
    try:
        for line in iter(proc.stdout.readline, ""):
            if not line:
                break
            buf.append(line.rstrip())
            buf = buf[-200:]
            st = RUNNERS.get(pid)
            if st and st.get("proc") is proc:
                st["runtime_log"] = "\n".join(buf)
    except Exception:
        pass


def _kill_proc(proc):
    if not proc:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass
    try:
        proc.wait(timeout=5)
    except Exception:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def _drop_preview_db(pid: str):
    if not _MONGO.get("url"):
        return
    try:
        import pymongo
        c = pymongo.MongoClient(_MONGO["url"], serverSelectionTimeoutMS=2000)
        c.drop_database(f"preview_{pid}")
        c.close()
    except Exception:
        pass


def stop(pid: str):
    st = RUNNERS.pop(pid, None)
    if st and st.get("proc"):
        _kill_proc(st["proc"])
    _drop_preview_db(pid)
    shutil.rmtree(work_dir(pid), ignore_errors=True)


def shutdown_all():
    for pid in list(RUNNERS):
        st = RUNNERS.get(pid)
        if st and st.get("proc"):
            _kill_proc(st["proc"])
    if _MONGO.get("proc"):
        _kill_proc(_MONGO["proc"])


async def _scan(pid: str) -> tuple[bool, str]:
    """Light signature of backend/ files from the DB, without touching disk."""
    files = await core.db.files.find(
        {"project_id": pid, "path": {"$regex": "^backend/"}}, {"_id": 0}).sort("path", 1).to_list(5000)
    has_backend = any(f["path"] == "backend/server.py" for f in files)
    sig = hashlib.sha256()
    for f in files:
        if any(part in SKIP_DIRS for part in f["path"].split("/")):
            continue
        sig.update(f["path"].encode())
        sig.update((f.get("content") or "").encode())
        sig.update((f.get("storage_path") or "").encode())
    return has_backend, sig.hexdigest()


async def ensure(pid: str, env_vars: dict, force: bool = False) -> dict:
    """Sync files and (re)start the backend if needed. Idempotent and cheap on the hot path."""
    lock = _lock(pid)
    if not lock.acquire(blocking=False):
        return status(pid)
    try:
        has_backend, sig = await _scan(pid)
        if not has_backend:
            stop(pid)
            RUNNERS[pid] = {"status": "no_backend", "sig": sig, "last_active": _now()}
            return status(pid)
        st = RUNNERS.get(pid)
        crashed = st and st.get("proc") and st["proc"].poll() is not None
        if not force and st and st.get("status") in ("running", "installing", "starting") and st.get("sig") == sig and not crashed:
            st["last_active"] = _now()
            return status(pid)
        old = RUNNERS.get(pid)
        if old and old.get("proc"):
            _kill_proc(old["proc"])
        await sync_files(pid)
        RUNNERS[pid] = {"status": "starting", "sig": sig,
                        "token": (old or {}).get("token") or secrets.token_urlsafe(24),
                        "proc": None, "port": None, "log": "", "runtime_log": "",
                        "started": _now(), "last_active": _now()}
        threading.Thread(target=_install_and_launch, args=(pid, env_vars), daemon=True).start()
        return status(pid)
    finally:
        lock.release()


def touch(pid: str):
    st = RUNNERS.get(pid)
    if st:
        st["last_active"] = _now()


def status(pid: str) -> dict:
    st = RUNNERS.get(pid)
    if not st:
        return {"status": "stopped"}
    return {"status": st["status"], "token": st.get("token"),
            "log": st.get("log", ""), "runtime_log": st.get("runtime_log", "")}


def public_status(pid: str) -> dict:
    """Status for anonymous Live Preview visitors: token to use the proxy, but no logs."""
    st = RUNNERS.get(pid)
    if not st:
        return {"status": "stopped"}
    return {"status": st["status"], "token": st.get("token")}


def reaper_loop():
    import time
    while True:
        time.sleep(60)
        for pid in list(RUNNERS):
            st = RUNNERS.get(pid)
            if not st:
                continue
            if st.get("proc") and st["proc"].poll() is not None and st.get("status") == "running":
                st["status"] = "error"
                st.setdefault("log", "")
                st["log"] += "\nO processo do backend parou."
            if _now() - st.get("last_active", 0) > IDLE_SECONDS:
                logger.info("Reaping idle preview %s", pid)
                stop(pid)


async def proxy(pid: str, method: str, subpath: str, request):
    from fastapi import Response
    st = RUNNERS.get(pid)
    if not st or st.get("status") != "running" or not st.get("port"):
        raise HTTPException(status_code=503, detail="O backend da prévia não está rodando.")
    touch(pid)
    url = f"http://127.0.0.1:{st['port']}/{subpath}"
    body = await request.body()
    drop = {"host", "content-length", "authorization", "x-preview-token", "cookie", "accept-encoding"}
    headers = {k: v for k, v in request.headers.items() if k.lower() not in drop}
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.request(method, url, content=body, params=dict(request.query_params), headers=headers)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Falha ao falar com o backend da prévia: {e}")
    skip = {"content-length", "transfer-encoding", "content-encoding", "connection"}
    resp_headers = {k: v for k, v in r.headers.items() if k.lower() not in skip}
    return Response(content=r.content, status_code=r.status_code, headers=resp_headers,
                    media_type=r.headers.get("content-type"))
