# Iteration 13: preview runner retest - env/DB isolation, venv reuse, forced restart, public run, delete cleanup
import os
import time
import subprocess
import pytest
import requests
from conftest import BASE_URL

API = f"{BASE_URL}/api"
ALLOWED = {"PIP_DISABLE_PIP_VERSION_CHECK", "PIP_NO_CACHE_DIR", "PYTHONPATH", "DONAS_ALLOW_PORTS", "DB_NAME", "HOME", "LANG", "LC_ALL", "MONGO_URL", "PATH", "PORT", "PYTHONUNBUFFERED", "VIRTUAL_ENV"}

SERVER = '''import os
from fastapi import FastAPI
from pymongo import MongoClient
app = FastAPI()
MSG = "%s"

@app.get("/api/ping")
def ping():
    return {"msg": MSG}

@app.get("/api/env")
def env():
    return {"keys": sorted(os.environ.keys()), "mongo": os.environ.get("MONGO_URL"), "db": os.environ.get("DB_NAME")}

@app.get("/api/dbs")
def dbs():
    c = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=3000)
    c[os.environ["DB_NAME"]].items.insert_one({"x": 1})
    return {"dbs": c.list_database_names()}

@app.get("/api/probe")
def probe():
    out = {}
    try:
        out["dotenv_readable"] = "MONGO_URL" in open("/app/backend/.env").read()
    except Exception as e:
        out["dotenv_readable"] = False
    try:
        c = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=2000)
        out["platform_dbs"] = c.list_database_names()
    except Exception as e:
        out["platform_dbs"] = None
    try:
        out["proc1_environ_secret"] = b"CLERK" in open("/proc/1/environ", "rb").read()
    except Exception:
        out["proc1_environ_secret"] = False
    return out
'''
REQS = "fastapi\nuvicorn\npymongo\n"


def put(member, pid, path, content):
    r = member.put(f"{API}/projects/{pid}/files", json={"path": path, "content": content})
    assert r.status_code == 200, r.text


def wait_running(member, pid, timeout=180):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        last = member.get(f"{API}/projects/{pid}/preview/status").json()
        if last["status"] in ("running", "error"):
            return last, time.time() - t0
        time.sleep(1.5)
    return last, time.time() - t0


def uvicorn_procs(pid):
    out = subprocess.run(["ps", "-eo", "pid,stat,args", "--width", "1000"], capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if "uvicorn server:app" in l and "grep" not in l], out


def cwd_of(ps_pid):
    try:
        return os.readlink(f"/proc/{ps_pid}/cwd")
    except Exception:
        return ""


def project_uvicorns(pid):
    lines, _ = uvicorn_procs(pid)
    res = []
    for l in lines:
        p = l.split()[0]
        if pid in cwd_of(p) or f"/{pid}/" in l:  # /proc/<pid>/cwd unreadable for setpriv'd uids
            res.append(l)
    return res


@pytest.fixture(scope="module")
def proj(member, created_projects):
    r = member.post(f"{API}/projects", json={"name": "TEST_iter13_isolation"})
    assert r.status_code == 200
    pid = r.json()["id"]
    created_projects.append(pid)
    put(member, pid, "backend/server.py", SERVER % "AAAA")
    put(member, pid, "backend/requirements.txt", REQS)
    e = member.put(f"{API}/projects/{pid}/env", json={"vars": [{"key": "MY_APP_VAR", "value": "hello"}]})
    assert e.status_code == 200, e.text
    d = member.post(f"{API}/projects/{pid}/preview/run").json()
    st, took = wait_running(member, pid)
    print(f"first run {took:.1f}s")
    assert st["status"] == "running", st.get("log")
    return {"pid": pid, "token": st["token"]}


def get(proj, path):
    return requests.get(f"{API}/projects/{proj['pid']}/preview/proxy/{path}", headers={"X-Preview-Token": proj["token"]})


class TestIsolation:
    def test_env_minimal(self, proj):
        r = get(proj, "api/env")
        assert r.status_code == 200, r.text
        keys = set(r.json()["keys"])
        print("ENV KEYS:", sorted(keys))
        extra = keys - ALLOWED - {"MY_APP_VAR"}
        assert not extra, f"unexpected env keys: {extra}"
        assert "MY_APP_VAR" in keys
        assert r.json()["db"] == f"preview_{proj['pid']}"
        assert "27017" not in r.json()["mongo"]

    def test_db_isolated(self, proj):
        r = get(proj, "api/dbs")
        assert r.status_code == 200, r.text
        dbs = r.json()["dbs"]
        print("DBS:", dbs)
        assert "test_database" not in dbs
        assert f"preview_{proj['pid']}" in dbs

    def test_residual_probe(self, proj):
        """Report-only: what else user code can reach on the host."""
        r = get(proj, "api/probe")
        assert r.status_code == 200, r.text
        print("PROBE:", r.json())


class TestRestart:
    def test_forced_restart_keeps_venv_single_proc(self, member, proj):
        pid = proj["pid"]
        r = member.post(f"{API}/projects/{pid}/preview/run?restart=1")
        assert r.status_code == 200
        assert r.json()["status"] in ("starting", "installing"), r.json()
        st, took = wait_running(member, pid)
        print(f"forced restart {took:.1f}s")
        assert st["status"] == "running"
        assert os.path.isdir(f"/tmp/donas_previews/{pid}/.venv")
        time.sleep(1)
        procs = project_uvicorns(pid)
        print("UVICORN for project:", procs)
        assert len(procs) == 1, procs
        _, allps = uvicorn_procs(pid)
        assert not [l for l in allps.splitlines() if " Z" in l and ("uvicorn" in l or "defunct" in l)], "zombies"

    def test_same_length_edit_restarts(self, member, proj):
        pid = proj["pid"]
        put(member, pid, "backend/server.py", SERVER % "BBBB")
        r = member.post(f"{API}/projects/{pid}/preview/run")
        assert r.json()["status"] in ("starting", "installing"), r.json()
        st, took = wait_running(member, pid)
        assert st["status"] == "running"
        assert get(proj, "api/ping").json()["msg"] == "BBBB"

    def test_unchanged_run_idempotent(self, member, proj):
        r = member.post(f"{API}/projects/{proj['pid']}/preview/run")
        assert r.json()["status"] == "running"


class TestPublic:
    def test_public_run_no_logs_and_rate_limit(self, member, proj):
        pid = proj["pid"]
        assert member.patch(f"{API}/projects/{pid}", json={"public_preview": True}).status_code == 200
        r = requests.post(f"{API}/public/projects/{pid}/preview/run")
        assert r.status_code == 200
        assert set(r.json().keys()) == {"status", "token"}, r.json()
        codes = [requests.post(f"{API}/public/projects/{pid}/preview/run").status_code for _ in range(22)]
        print("codes:", codes)
        assert 429 in codes


class TestDeleteCleanup:
    def test_delete_cleans(self, member, created_projects):
        r = member.post(f"{API}/projects", json={"name": "TEST_iter13_delete"})
        pid = r.json()["id"]
        created_projects.append(pid)
        put(member, pid, "backend/server.py", SERVER % "DDDD")
        put(member, pid, "backend/requirements.txt", REQS)
        member.post(f"{API}/projects/{pid}/preview/run")
        st, _ = wait_running(member, pid)
        assert st["status"] == "running", st.get("log")
        tok = st["token"]
        d = requests.get(f"{API}/projects/{pid}/preview/proxy/api/dbs", headers={"X-Preview-Token": tok}).json()
        assert f"preview_{pid}" in d["dbs"]
        # a sibling check: can this project see other preview dbs? (cross-tenant)
        others = [x for x in d["dbs"] if x.startswith("preview_") and x != f"preview_{pid}"]
        print("OTHER PREVIEW DBS VISIBLE:", others)
        assert member.delete(f"{API}/projects/{pid}").status_code == 200
        time.sleep(1)
        assert not os.path.exists(f"/tmp/donas_previews/{pid}")
        assert project_uvicorns(pid) == []
        import runner_check
        assert f"preview_{pid}" not in runner_check.preview_dbs()


class TestSmoke:
    def test_me(self, member):
        assert member.get(f"{API}/me").status_code == 200

    def test_models(self, member):
        assert member.get(f"{API}/models").status_code == 200

    def test_project_crud(self, member):
        r = member.post(f"{API}/projects", json={"name": "TEST_iter13_crud"})
        pid = r.json()["id"]
        assert member.patch(f"{API}/projects/{pid}", json={"name": "TEST_iter13_crud2"}).status_code == 200
        assert member.get(f"{API}/projects/{pid}").json()["project"]["name"] == "TEST_iter13_crud2"
        assert member.delete(f"{API}/projects/{pid}").status_code == 200
        assert member.get(f"{API}/projects/{pid}").status_code == 404
