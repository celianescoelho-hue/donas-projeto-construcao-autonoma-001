# Iteration 14: preview sandbox (uid, .env, platform mongo, per-project mongo auth, cross-project fs), env restart, public run/status, stop/delete
import os
import time
import pytest
import requests
from conftest import BASE_URL

API = f"{BASE_URL}/api"

PROBE = r'''import os, subprocess, sys
from fastapi import FastAPI
from pymongo import MongoClient
app = FastAPI()

def _try(fn):
    try:
        return {"ok": True, "v": fn()}
    except Exception as e:
        return {"ok": False, "err": type(e).__name__ + ": " + str(e)[:160]}

@app.get("/api/whoami")
def whoami():
    return {"uid": os.getuid(), "gid": os.getgid(), "groups": os.getgroups(), "var": os.environ.get("NEW_VAR")}

@app.get("/api/probe")
def probe(other: str = ""):
    url = os.environ["MONGO_URL"]
    out = {}
    out["env_file"] = _try(lambda: open("/app/backend/.env").read()[:20])
    out["platform_mongo"] = _try(lambda: MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=2000).list_database_names())
    def w():
        c = MongoClient(url, serverSelectionTimeoutMS=3000)
        c[os.environ["DB_NAME"]].items.insert_one({"x": 1})
        return c[os.environ["DB_NAME"]].items.count_documents({})
    out["own_write"] = _try(w)
    out["own_dbs"] = _try(lambda: MongoClient(url, serverSelectionTimeoutMS=3000).list_database_names())
    out["admin_pw_file"] = _try(lambda: open("/tmp/donas_previews/.mongo_admin").read()[:4])
    out["mongo_dbpath"] = _try(lambda: os.listdir("/tmp/donas_previews/_mongo"))
    out["proc1_environ"] = _try(lambda: len(open("/proc/1/environ", "rb").read()))
    out["storage_dir"] = _try(lambda: os.listdir(os.environ.get("X_STORAGE", "/app/storage")))
    if other:
        out["other_dir"] = _try(lambda: os.listdir(f"/tmp/donas_previews/{other}"))
        out["other_server"] = _try(lambda: open(f"/tmp/donas_previews/{other}/backend/server.py").read()[:10])
        # own creds against other DB
        def cross():
            c = MongoClient(url, serverSelectionTimeoutMS=3000)
            return c[f"preview_{other}"].list_collection_names()
        out["other_db_with_own_creds"] = _try(cross)
        host = url.split("@")[1].split("/")[0]
        def other_auth():
            c = MongoClient(f"mongodb://p_{other}:guess@{host}/preview_{other}?authSource=preview_{other}", serverSelectionTimeoutMS=3000)
            return c[f"preview_{other}"].list_collection_names()
        out["other_db_guess_auth"] = _try(other_auth)
        def noauth():
            c = MongoClient(f"mongodb://{host}", serverSelectionTimeoutMS=3000)
            return c.list_database_names()
        out["preview_mongo_noauth"] = _try(noauth)
    # known-limitation probes: bypass the sitecustomize guard
    code = "import socket;s=socket.socket();s.settimeout(2);print(s.connect_ex(('127.0.0.1',27017)))"
    out["bypass_python_S"] = _try(lambda: subprocess.run([sys.executable, "-S", "-c", code], capture_output=True, text=True, timeout=10).stdout.strip())
    out["bypass_env_clear"] = _try(lambda: subprocess.run([sys.executable, "-c", code], env={"PATH": "/usr/bin"}, capture_output=True, text=True, timeout=10).stdout.strip())
    out["bypass_bash"] = _try(lambda: subprocess.run(["bash", "-c", "(exec 3<>/dev/tcp/127.0.0.1/27017) && echo OPEN || echo CLOSED"], capture_output=True, text=True, timeout=10).stdout.strip())
    out["platform_api"] = _try(lambda: subprocess.run(["bash", "-c", "(exec 3<>/dev/tcp/127.0.0.1/8001) && echo OPEN || echo CLOSED"], capture_output=True, text=True, timeout=10).stdout.strip())
    return out

@app.get("/api/bypass_mongo")
def bypass_mongo():
    import site
    sp = [p for p in sys.path if p.endswith("site-packages")]
    code = ("import sys;sys.path[:0]=%r;import pymongo;c=pymongo.MongoClient('mongodb://127.0.0.1:27017',serverSelectionTimeoutMS=2000);"
            "print(c.list_database_names())") % sp
    r = subprocess.run([sys.executable, "-S", "-c", code], capture_output=True, text=True, timeout=20)
    return {"out": r.stdout.strip()[:300], "err": r.stderr.strip()[-200:]}
'''
REQS = "fastapi\nuvicorn\npymongo\n"


def put(member, pid, path, content):
    r = member.put(f"{API}/projects/{pid}/files", json={"path": path, "content": content})
    assert r.status_code == 200, r.text


def wait_running(member, pid, timeout=200):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        last = member.get(f"{API}/projects/{pid}/preview/status").json()
        if last["status"] in ("running", "error"):
            return last
        time.sleep(1.5)
    return last


def mk(member, created, name):
    pid = member.post(f"{API}/projects", json={"name": name}).json()["id"]
    created.append(pid)
    put(member, pid, "backend/server.py", PROBE)
    put(member, pid, "backend/requirements.txt", REQS)
    member.post(f"{API}/projects/{pid}/preview/run")
    return pid


@pytest.fixture(scope="module")
def two(member, created_projects):
    a = mk(member, created_projects, "TEST_iter14_A")
    b = mk(member, created_projects, "TEST_iter14_B")
    sa, sb = wait_running(member, a), wait_running(member, b)
    assert sa["status"] == "running", sa.get("log")
    assert sb["status"] == "running", sb.get("log")
    return {"a": a, "b": b, "ta": sa["token"], "tb": sb["token"]}


def g(pid, tok, path, **params):
    return requests.get(f"{API}/projects/{pid}/preview/proxy/{path}", headers={"X-Preview-Token": tok}, params=params, timeout=60)


@pytest.fixture(scope="module")
def probe(two):
    # B must have its DB created
    g(two["b"], two["tb"], "api/probe")
    r = g(two["a"], two["ta"], "api/probe", other=two["b"])
    assert r.status_code == 200, r.text
    print("PROBE:", r.json())
    return r.json()


class TestSandbox:
    def test_uid_unprivileged_and_distinct(self, two):
        ua = g(two["a"], two["ta"], "api/whoami").json()
        ub = g(two["b"], two["tb"], "api/whoami").json()
        print(ua, ub)
        assert 20000 <= ua["uid"] < 60000 and 20000 <= ub["uid"] < 60000
        assert ua["uid"] != ub["uid"]
        assert ua["groups"] == []

    def test_env_file_blocked(self, probe):
        assert not probe["env_file"]["ok"] and "PermissionError" in probe["env_file"]["err"]

    def test_platform_mongo_blocked(self, probe):
        assert not probe["platform_mongo"]["ok"]

    def test_own_dbs_only(self, probe, two):
        assert probe["own_dbs"]["ok"], probe["own_dbs"]
        assert probe["own_dbs"]["v"] == [f"preview_{two['a']}"]

    def test_own_write(self, probe):
        assert probe["own_write"]["ok"] and probe["own_write"]["v"] >= 1

    def test_other_dir_blocked(self, probe):
        assert not probe["other_dir"]["ok"]
        assert not probe["other_server"]["ok"]

    def test_other_db_blocked(self, probe):
        assert not probe["other_db_with_own_creds"]["ok"]
        assert not probe["other_db_guess_auth"]["ok"]
        nd = probe["preview_mongo_noauth"]
        assert not nd["ok"] or nd["v"] == [], nd

    def test_admin_secrets_blocked(self, probe):
        assert not probe["admin_pw_file"]["ok"]
        assert not probe["mongo_dbpath"]["ok"]
        assert not probe["proc1_environ"]["ok"]

    def test_report_bypasses(self, probe, two):
        for k in ("bypass_python_S", "bypass_env_clear", "bypass_bash", "platform_api", "storage_dir"):
            print(k, probe[k])
        print("BYPASS_MONGO:", g(two["a"], two["ta"], "api/bypass_mongo").json())


class TestEnvRestart:
    def test_env_change_restarts(self, member, two):
        pid = two["a"]
        assert member.put(f"{API}/projects/{pid}/env", json={"vars": [{"key": "NEW_VAR", "value": "v14"}]}).status_code == 200
        r = member.post(f"{API}/projects/{pid}/preview/run").json()
        assert r["status"] in ("starting", "installing"), r
        st = wait_running(member, pid)
        assert st["status"] == "running"
        assert g(pid, st["token"], "api/whoami").json()["var"] == "v14"
        two["ta"] = st["token"]


class TestPublic:
    def test_public_status_and_run(self, member, two):
        pid = two["b"]
        assert member.patch(f"{API}/projects/{pid}", json={"public_preview": True}).status_code == 200
        s = requests.get(f"{API}/public/projects/{pid}/preview/status")
        assert s.status_code == 200 and set(s.json()) == {"status", "token"}, s.json()
        assert s.json()["status"] == "running"
        # private project -> 404
        s2 = requests.get(f"{API}/public/projects/{two['a']}/preview/status")
        assert s2.status_code == 404

    def test_rate_limit_rightmost_xff(self, two):
        pid = two["b"]
        # spoofed leftmost XFF must not escape the limit
        codes = [requests.post(f"{API}/public/projects/{pid}/preview/run",
                               headers={"X-Forwarded-For": f"9.9.9.{i}"}).status_code for i in range(24)]
        print("codes", codes)
        assert 429 in codes

    def test_public_proxy_works(self, two):
        s = requests.get(f"{API}/public/projects/{two['b']}/preview/status").json()
        r = requests.get(f"{API}/public/projects/{two['b']}/preview/proxy/api/whoami", headers={"X-Preview-Token": s["token"]})
        assert r.status_code == 200 and "uid" in r.json()


class TestStopDelete:
    def test_stop_drops_db_and_proc(self, member, two):
        pid = two["b"]
        t0 = time.time()
        # concurrent health request must not stall while stop runs
        r = member.post(f"{API}/projects/{pid}/preview/stop")
        print("stop took", time.time() - t0)
        assert r.status_code == 200
        assert member.get(f"{API}/projects/{pid}/preview/status").json()["status"] == "stopped"
        assert not os.path.exists(f"/tmp/donas_previews/{pid}")
        # A cannot see B's db anyway; check from A that DB list is still only its own
        r = g(two["a"], two["ta"], "api/probe").json()
        assert r["own_dbs"]["v"] == [f"preview_{two['a']}"]

    def test_delete_cleans(self, member, two, created_projects):
        pid = two["a"]
        assert member.delete(f"{API}/projects/{pid}").status_code == 200
        time.sleep(1)
        assert not os.path.exists(f"/tmp/donas_previews/{pid}")
        assert member.get(f"{API}/projects/{pid}").status_code == 404
        import runner_check
        dbs = runner_check.preview_dbs()
        assert f"preview_{pid}" not in dbs and f"preview_{two['b']}" not in dbs, dbs
        users = runner_check.preview_users()
        assert f"p_{pid}" not in users and f"p_{two['b']}" not in users, users
