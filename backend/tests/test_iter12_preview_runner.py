# Iteration 12: full-stack preview runner (run/status/proxy/public/delete) + smoke regression
import os
import time
import pytest
import requests
from conftest import BASE_URL

API = f"{BASE_URL}/api"

SERVER_TMPL = '''import os
from fastapi import FastAPI, Request
app = FastAPI()

@app.get("/api/ping")
async def ping():
    return {"msg": "%s", "db": os.environ.get("DB_NAME")}

@app.post("/api/echo")
async def echo(req: Request):
    body = await req.json()
    return {"got": body, "q": dict(req.query_params), "has_tok": "x-preview-token" in req.headers}

@app.get("/api/envcheck")
async def envcheck():
    keys = ["CLERK_SECRET_KEY", "OPENROUTER_API_KEY", "EMERGENT_LLM_KEY", "JWT_SECRET", "ENCRYPTION_KEY", "FERNET_KEY", "GITHUB_CLIENT_SECRET"]
    return {"leaked": sorted([k for k in os.environ if any(s in k for s in ("SECRET", "KEY", "TOKEN", "PASSWORD"))]),
            "mongo_same": os.environ.get("MONGO_URL") is not None}
'''
REQS = "fastapi\nuvicorn\n"
APP_JS = '''import { useEffect, useState } from "react";
export default function App(){
  const [m,setM]=useState("carregando");
  useEffect(()=>{fetch("/api/ping").then(r=>r.json()).then(d=>setM(d.msg)).catch(e=>setM("ERR "+e.message));},[]);
  return <div data-testid="msg">{m}</div>;
}
'''


def put(member, pid, path, content):
    r = member.put(f"{API}/projects/{pid}/files", json={"path": path, "content": content})
    assert r.status_code == 200, r.text


def new_project(member, created, name):
    r = member.post(f"{API}/projects", json={"name": name})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    created.append(pid)
    return pid


def wait_running(member, pid, timeout=150):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        last = member.get(f"{API}/projects/{pid}/preview/status").json()
        if last["status"] in ("running", "error"):
            return last, time.time() - t0
        time.sleep(2)
    return last, time.time() - t0


@pytest.fixture(scope="module")
def fullstack(member, created_projects):
    pid = new_project(member, created_projects, "TEST_runner_fullstack")
    put(member, pid, "backend/server.py", SERVER_TMPL % "pong v1")
    put(member, pid, "backend/requirements.txt", REQS)
    put(member, pid, "frontend/src/App.js", APP_JS)
    r = member.post(f"{API}/projects/{pid}/preview/run")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] in ("installing", "starting"), d
    assert d.get("token")
    st, took = wait_running(member, pid)
    print(f"first run took {took:.1f}s -> {st['status']}")
    assert st["status"] == "running", st.get("log")
    return {"pid": pid, "token": d["token"]}


class TestRunnerLifecycle:
    def test_proxy_ping_with_token(self, fullstack):
        r = requests.get(f"{API}/projects/{fullstack['pid']}/preview/proxy/api/ping",
                         headers={"X-Preview-Token": fullstack["token"]})
        assert r.status_code == 200, r.text
        assert r.json() == {"msg": "pong v1", "db": f"preview_{fullstack['pid']}"}

    def test_proxy_without_token_401(self, fullstack):
        r = requests.get(f"{API}/projects/{fullstack['pid']}/preview/proxy/api/ping")
        assert r.status_code == 401

    def test_proxy_wrong_token_401(self, fullstack):
        r = requests.get(f"{API}/projects/{fullstack['pid']}/preview/proxy/api/ping", headers={"X-Preview-Token": "nope"})
        assert r.status_code == 401

    def test_proxy_ptok_query(self, fullstack):
        r = requests.get(f"{API}/projects/{fullstack['pid']}/preview/proxy/api/ping?ptok={fullstack['token']}")
        assert r.status_code == 200
        assert r.json()["msg"] == "pong v1"

    def test_proxy_post_body_and_query(self, fullstack):
        r = requests.post(f"{API}/projects/{fullstack['pid']}/preview/proxy/api/echo?a=1",
                          json={"x": 42}, headers={"X-Preview-Token": fullstack["token"]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["got"] == {"x": 42}
        assert d["q"].get("a") == "1"
        assert d["has_tok"] is False

    def test_proxy_preflight_options(self, fullstack):
        r = requests.options(f"{API}/projects/{fullstack['pid']}/preview/proxy/api/ping",
                             headers={"Origin": "null", "Access-Control-Request-Method": "GET",
                                      "Access-Control-Request-Headers": "x-preview-token"})
        assert r.status_code == 200, r.text

    def test_status_requires_auth(self, fullstack):
        r = requests.get(f"{API}/projects/{fullstack['pid']}/preview/status")
        assert r.status_code in (401, 403)

    def test_run_idempotent_same_token(self, member, fullstack):
        r = member.post(f"{API}/projects/{fullstack['pid']}/preview/run")
        assert r.json()["status"] == "running"
        assert r.json()["token"] == fullstack["token"]

    def test_env_isolation_report(self, fullstack):
        """SECURITY: user backend should not inherit platform secrets."""
        r = requests.get(f"{API}/projects/{fullstack['pid']}/preview/proxy/api/envcheck",
                         headers={"X-Preview-Token": fullstack["token"]})
        assert r.status_code == 200
        leaked = r.json()["leaked"]
        print("SECRET-LIKE ENV KEYS VISIBLE TO USER BACKEND:", leaked)
        assert leaked == [], f"platform env leaked to user code: {leaked}"

    def test_edit_restart_reflects_new_message(self, member, fullstack):
        pid = fullstack["pid"]
        put(member, pid, "backend/server.py", SERVER_TMPL % "pong v2 editado")
        r = member.post(f"{API}/projects/{pid}/preview/run")
        assert r.json()["status"] in ("installing", "starting"), r.json()
        st, took = wait_running(member, pid)
        print(f"restart took {took:.1f}s")
        assert st["status"] == "running", st.get("log")
        r = requests.get(f"{API}/projects/{pid}/preview/proxy/api/ping", headers={"X-Preview-Token": r.json()["token"]})
        assert r.status_code == 200
        assert r.json()["msg"] == "pong v2 editado"

    def test_restart_reuses_venv_fast(self, member, fullstack):
        pid = fullstack["pid"]
        put(member, pid, "backend/server.py", SERVER_TMPL % "pong v3")
        member.post(f"{API}/projects/{pid}/preview/run")
        st, took = wait_running(member, pid)
        print(f"restart #2 took {took:.1f}s")
        assert st["status"] == "running"
        assert took < 15, f"restart took {took:.1f}s - venv apparently NOT reused"


class TestNoBackend:
    def test_no_backend(self, member, created_projects):
        pid = new_project(member, created_projects, "TEST_runner_frontonly")
        put(member, pid, "frontend/src/App.js", "export default function App(){return <div>oi</div>}")
        r = member.post(f"{API}/projects/{pid}/preview/run")
        assert r.status_code == 200
        assert r.json()["status"] == "no_backend"
        assert not r.json().get("token")
        p = requests.get(f"{API}/projects/{pid}/preview/proxy/api/ping", headers={"X-Preview-Token": "x"})
        assert p.status_code in (401, 503)


class TestPublicAndDelete:
    def test_public_run_proxy_then_delete(self, member):
        pid = member.post(f"{API}/projects", json={"name": "TEST_runner_public"}).json()["id"]
        try:
            put(member, pid, "backend/server.py", SERVER_TMPL % "pong publico")
            put(member, pid, "backend/requirements.txt", REQS)
            put(member, pid, "frontend/src/App.js", APP_JS)
            # not public yet -> 404
            assert requests.post(f"{API}/public/projects/{pid}/preview/run").status_code == 404
            assert member.patch(f"{API}/projects/{pid}", json={"public_preview": True}).status_code == 200
            pv = requests.get(f"{API}/public/projects/{pid}/preview")
            assert pv.status_code == 200
            assert not any(f["path"].startswith("backend/") for f in pv.json()["files"])
            d = requests.post(f"{API}/public/projects/{pid}/preview/run").json()
            assert d.get("token"), d
            t0 = time.time()
            while d["status"] in ("installing", "starting") and time.time() - t0 < 150:
                time.sleep(3)
                d = requests.post(f"{API}/public/projects/{pid}/preview/run").json()
            assert d["status"] == "running", d
            print("PUBLIC run response keys:", list(d.keys()), "log len:", len(d.get("log") or ""))
            r = requests.get(f"{API}/public/projects/{pid}/preview/proxy/api/ping", headers={"X-Preview-Token": d["token"]})
            assert r.status_code == 200 and r.json()["msg"] == "pong publico"
            assert requests.get(f"{API}/public/projects/{pid}/preview/proxy/api/ping").status_code == 401
            tok = d["token"]
        finally:
            dr = member.delete(f"{API}/projects/{pid}")
        assert dr.status_code == 200
        assert member.get(f"{API}/projects/{pid}/preview/status").status_code == 404
        r = requests.get(f"{API}/projects/{pid}/preview/proxy/api/ping", headers={"X-Preview-Token": tok})
        assert r.status_code == 401
        assert requests.post(f"{API}/public/projects/{pid}/preview/run").status_code == 404


class TestSmoke:
    def test_me(self, member):
        r = member.get(f"{API}/me")
        assert r.status_code == 200 and r.json().get("email")

    def test_models(self, member):
        r = member.get(f"{API}/models")
        assert r.status_code == 200

    def test_projects_list(self, member):
        r = member.get(f"{API}/projects")
        assert r.status_code == 200 and isinstance(r.json(), list)
