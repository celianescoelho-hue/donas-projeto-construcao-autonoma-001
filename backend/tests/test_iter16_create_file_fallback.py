# Iteration 16: create_file overwrite without 60-line limit (direct Agent.run_tool), fallback unit, no auto-run backend status
import asyncio
import base64
import subprocess
import sys
import requests
from conftest import BASE_URL

sys.path.insert(0, "/app/backend")
API = f"{BASE_URL}/api"

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def _run_tool(pid, user_id, name, args):
    """Run Agent.run_tool in a fresh event loop with a fresh motor client."""
    code = (
        "import asyncio,sys,json;sys.path.insert(0,'/app/backend');"
        "from dotenv import load_dotenv;load_dotenv('/app/backend/.env');"
        "from agent import Agent;"
        f"a=Agent({{'id':'{pid}'}},{{'user_id':'{user_id}'}},asyncio.Queue());"
        f"print(asyncio.run(a.run_tool({name!r}, json.loads({__import__('json').dumps(__import__('json').dumps(args))}))))"
    )
    out = subprocess.run(["python", "-c", code], capture_output=True, text=True, timeout=60)
    return (out.stdout.strip() or out.stderr[-400:])


def _file(member, pid, path):
    files = member.get(f"{API}/projects/{pid}").json()["files"]
    return next((f for f in files if f["path"] == path), None)


def test_create_file_overwrite_large(member, created_projects):
    me = member.get(f"{API}/me").json()
    uid = me.get("user_id") or me.get("user", {}).get("user_id")
    assert uid
    pid = member.post(f"{API}/projects", json={"name": "TEST_iter16_createfile"}).json()["id"]
    created_projects.append(pid)
    big = "\n".join(f"linha original {i}" for i in range(120))
    r = member.put(f"{API}/projects/{pid}/files", json={"path": "notes.txt", "content": big})
    assert r.status_code == 200
    new = "\n".join(f"TEXTO NOVO {i}" for i in range(150))
    res = _run_tool(pid, uid, "create_file", {"path": "notes.txt", "content": new})
    print("overwrite:", res)
    assert res.startswith("OK") and "reescrito" in res
    f = _file(member, pid, "notes.txt")
    assert f["content"] == new

    # empty content on existing file -> ERRO, unchanged
    res = _run_tool(pid, uid, "create_file", {"path": "notes.txt", "content": "   "})
    print("empty:", res)
    assert res.startswith("ERRO")
    assert _file(member, pid, "notes.txt")["content"] == new

    # new file -> criado
    res = _run_tool(pid, uid, "create_file", {"path": "src/novo.js", "content": "export const a = 1;\n"})
    print("new:", res)
    assert res.startswith("OK") and "criado" in res

    # binary asset overwrite -> ERRO
    up = member.post(f"{API}/projects/{pid}/upload", files=[("files", ("logo.png", PNG, "image/png"))], data={"directory": "assets"})
    assert up.status_code == 200, up.text
    bpath = up.json()["saved"][0]["path"]
    res = _run_tool(pid, uid, "create_file", {"path": bpath, "content": "texto"})
    print("binary:", res)
    assert res.startswith("ERRO")
    assert _file(member, pid, bpath)["kind"] == "binary"


def test_fallback_unit_script():
    out = subprocess.run(["python", "/app/backend/tests/test_model_fallback.py"], capture_output=True, text=True, timeout=60, cwd="/app/backend")
    print(out.stdout)
    assert "models tried: ['qwen/qwen3-coder-next', 'qwen/qwen3-coder']" in out.stdout
    assert out.stdout.strip().endswith("OK")


def test_status_does_not_start(member, created_projects):
    pid = member.post(f"{API}/projects", json={"name": "TEST_iter16_status"}).json()["id"]
    created_projects.append(pid)
    member.put(f"{API}/projects/{pid}/files", json={"path": "backend/server.py", "content": "from fastapi import FastAPI\napp = FastAPI()\n"})
    for _ in range(3):
        st = member.get(f"{API}/projects/{pid}/preview/status").json()
        assert st["status"] == "stopped", st
    assert not st.get("token")
