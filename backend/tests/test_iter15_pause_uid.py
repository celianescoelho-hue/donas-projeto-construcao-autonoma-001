# Iteration 15: unique persisted preview_uid, pause keeps venv+data, concurrent run returns 'starting', creds file perms, delete cleanup, smoke
import os
import glob
import time
import threading
import pytest
import requests
from pymongo import MongoClient
from dotenv import dotenv_values
from conftest import BASE_URL
from test_iter14_sandbox import PROBE, REQS, put, wait_running, g

API = f"{BASE_URL}/api"
_benv = dotenv_values("/app/backend/.env")

EXTRA = r'''

@app.get("/api/perms")
def perms():
    import glob as _g
    out = {"creds": _try(lambda: open("/app/memory/test_credentials.md").read()[:10]),
           "memory_ls": _try(lambda: os.listdir("/app/memory")),
           "supervisor_ls": _try(lambda: os.listdir("/etc/supervisor/conf.d"))}
    for f in ["/etc/supervisor/conf.d/supervisord.conf", "/etc/supervisor/conf.d/supervisord_code_server.conf"]:
        out[f] = _try(lambda: open(f).read()[:10])
    out["env"] = _try(lambda: open("/app/backend/.env").read()[:10])
    return out

@app.get("/api/count")
def count():
    c = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=3000)
    return {"n": c[os.environ["DB_NAME"]].marks.count_documents({})}

@app.post("/api/mark")
def mark():
    c = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=3000)
    c[os.environ["DB_NAME"]].marks.insert_one({"m": 1})
    return {"n": c[os.environ["DB_NAME"]].marks.count_documents({})}
'''


def pdb():
    return MongoClient(_benv["MONGO_URL"])[_benv["DB_NAME"]]


def mk(member, created, name):
    pid = member.post(f"{API}/projects", json={"name": name}).json()["id"]
    created.append(pid)
    put(member, pid, "backend/server.py", PROBE + EXTRA)
    put(member, pid, "backend/requirements.txt", REQS)
    member.post(f"{API}/projects/{pid}/preview/run")
    return pid


@pytest.fixture(scope="module")
def two(member, created_projects):
    a = mk(member, created_projects, "TEST_iter15_A")
    b = mk(member, created_projects, "TEST_iter15_B")
    sa, sb = wait_running(member, a), wait_running(member, b)
    assert sa["status"] == "running", sa.get("log")
    assert sb["status"] == "running", sb.get("log")
    return {"a": a, "b": b, "ta": sa["token"], "tb": sb["token"]}


class TestUid:
    def test_unique_persisted(self, two):
        ua = g(two["a"], two["ta"], "api/whoami").json()["uid"]
        ub = g(two["b"], two["tb"], "api/whoami").json()["uid"]
        da = pdb().projects.find_one({"id": two["a"]})["preview_uid"]
        db_ = pdb().projects.find_one({"id": two["b"]})["preview_uid"]
        print("uids", ua, ub, da, db_, pdb().counters.find_one({"_id": "preview_uid"}))
        assert ua == da and ub == db_ and ua != ub

    def test_rerun_reuses_uid(self, member, two):
        pid = two["a"]
        before = pdb().projects.find_one({"id": pid})["preview_uid"]
        r = member.post(f"{API}/projects/{pid}/preview/run?restart=1").json()
        assert r["status"] in ("starting", "installing"), r
        st = wait_running(member, pid)
        assert st["status"] == "running", st.get("log")
        two["ta"] = st["token"]
        assert g(pid, st["token"], "api/whoami").json()["uid"] == before


class TestPerms:
    def test_creds_and_supervisor_unreadable(self, two):
        p = g(two["a"], two["ta"], "api/perms").json()
        print("PERMS", p)
        for k, v in p.items():
            assert not v["ok"], (k, v)
        print("memory mode", oct(os.stat("/app/memory").st_mode), "conf.d", oct(os.stat("/etc/supervisor/conf.d").st_mode))


class TestPause:
    def test_stop_keeps_venv_and_data(self, member, two):
        pid = two["b"]
        n1 = g(pid, two["tb"], "api/mark", ).status_code  # GET -> 405
        r = requests.post(f"{API}/projects/{pid}/preview/proxy/api/mark", headers={"X-Preview-Token": two["tb"]}).json()
        n_before = r["n"]
        assert n_before >= 1
        assert member.post(f"{API}/projects/{pid}/preview/stop").status_code == 200
        assert member.get(f"{API}/projects/{pid}/preview/status").json()["status"] == "stopped"
        assert os.path.exists(f"/tmp/donas_previews/{pid}/.venv/bin/python")
        assert os.path.exists(f"/tmp/donas_previews/{pid}/backend/server.py")
        t0 = time.time()
        member.post(f"{API}/projects/{pid}/preview/run")
        st = wait_running(member, pid)
        print("restart after pause took", round(time.time() - t0, 1), "s")
        assert st["status"] == "running", st.get("log")
        two["tb"] = st["token"]
        n_after = g(pid, st["token"], "api/count").json()["n"]
        assert n_after == n_before, (n_before, n_after)

    def test_concurrent_public_run_returns_starting(self, member, two):
        pid = two["b"]
        assert member.patch(f"{API}/projects/{pid}", json={"public_preview": True}).status_code == 200
        assert member.post(f"{API}/projects/{pid}/preview/stop").status_code == 200
        res = []

        def call():
            res.append(requests.post(f"{API}/public/projects/{pid}/preview/run").json())
        ts = [threading.Thread(target=call) for _ in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        print("concurrent", res)
        assert all(r.get("status") in ("starting", "installing", "running") for r in res), res
        st = wait_running(member, pid)
        assert st["status"] == "running"
        two["tb"] = st["token"]


class TestSandboxRegression:
    def test_probe(self, two):
        p = g(two["a"], two["ta"], "api/probe", other=two["b"]).json()
        assert not p["platform_mongo"]["ok"]
        assert p["own_dbs"]["ok"] and p["own_dbs"]["v"] == [f"preview_{two['a']}"]
        assert not p["other_dir"]["ok"] and not p["other_server"]["ok"]
        assert not p["other_db_with_own_creds"]["ok"] and not p["other_db_guess_auth"]["ok"]
        assert not p["env_file"]["ok"]


class TestDelete:
    def test_delete_cleans(self, member, two):
        import runner_check
        for pid in (two["a"], two["b"]):
            assert member.delete(f"{API}/projects/{pid}").status_code == 200
        time.sleep(1)
        dbs = runner_check.preview_dbs()
        users = runner_check.preview_users()
        for pid in (two["a"], two["b"]):
            assert not os.path.exists(f"/tmp/donas_previews/{pid}")
            assert member.get(f"{API}/projects/{pid}").status_code == 404
            assert f"preview_{pid}" not in dbs and f"p_{pid}" not in users


class TestSmoke:
    def test_me_models_crud(self, member, created_projects):
        assert member.get(f"{API}/me").status_code == 200
        m = member.get(f"{API}/models")
        assert m.status_code == 200 and m.json()
        pid = member.post(f"{API}/projects", json={"name": "TEST_iter15_crud"}).json()["id"]
        created_projects.append(pid)
        assert member.patch(f"{API}/projects/{pid}", json={"name": "TEST_iter15_crud2"}).json()["name"] == "TEST_iter15_crud2"
        assert member.get(f"{API}/projects/{pid}").json()["project"]["name"] == "TEST_iter15_crud2"
        assert any(p["id"] == pid for p in member.get(f"{API}/projects").json())
        assert member.delete(f"{API}/projects/{pid}").status_code == 200
        assert member.get(f"{API}/projects/{pid}").status_code == 404
