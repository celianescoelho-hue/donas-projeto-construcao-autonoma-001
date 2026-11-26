# Iteration 15: stop (pause) while the backend is still installing must not leave an orphan uvicorn running
import time
import subprocess
import requests
from conftest import BASE_URL
from test_iter14_sandbox import PROBE, REQS, put, wait_running

API = f"{BASE_URL}/api"


def uvicorns(pid):
    out = subprocess.run(["ps", "-eo", "pid,cmd", "--width", "1000"], capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if f"donas_previews/{pid}/" in l and "uvicorn" in l]


def test_stop_during_install_no_orphan(member, created_projects):
    pid = member.post(f"{API}/projects", json={"name": "TEST_iter15_orphan"}).json()["id"]
    created_projects.append(pid)
    put(member, pid, "backend/server.py", PROBE)
    put(member, pid, "backend/requirements.txt", REQS)
    r = member.post(f"{API}/projects/{pid}/preview/run").json()
    print("run", r["status"])
    time.sleep(1.0)
    print("status before stop", member.get(f"{API}/projects/{pid}/preview/status").json()["status"])
    assert member.post(f"{API}/projects/{pid}/preview/stop").status_code == 200
    time.sleep(45)
    st = member.get(f"{API}/projects/{pid}/preview/status").json()["status"]
    procs = uvicorns(pid)
    print("status after", st, "procs", procs)
    member.delete(f"{API}/projects/{pid}")
    time.sleep(1)
    print("after delete procs", uvicorns(pid))
    assert not procs, f"orphan uvicorn after stop while installing: {procs}"
