# Manual check: uvicorn processes per project after forced restarts (no zombies)
import subprocess, time, sys, os, requests
sys.path.insert(0, "/app/backend/tests")
from conftest import BASE_URL
API = f"{BASE_URL}/api"
tok = subprocess.run(["python", "/app/backend/tests/clerk_token.py", "forja.member+clerk_test@example.com"], capture_output=True, text=True).stdout.strip()
s = requests.Session(); s.headers["Authorization"] = f"Bearer {tok}"
pid = s.post(f"{API}/projects", json={"name": "TEST_iter13_proc"}).json()["id"]
print("pid", pid)
try:
    s.put(f"{API}/projects/{pid}/files", json={"path": "backend/server.py", "content": "from fastapi import FastAPI\napp=FastAPI()\n@app.get('/api/ping')\ndef p():\n    return {'ok':1}\n"})
    s.put(f"{API}/projects/{pid}/files", json={"path": "backend/requirements.txt", "content": "fastapi\nuvicorn\n"})
    def wait():
        t0 = time.time()
        while time.time() - t0 < 180:
            st = s.get(f"{API}/projects/{pid}/preview/status").json()
            if st["status"] in ("running", "error"):
                return st["status"], round(time.time() - t0, 1)
            time.sleep(1)
    print(s.post(f"{API}/projects/{pid}/preview/run").json()["status"], wait())
    for i in range(3):
        print("restart", s.post(f"{API}/projects/{pid}/preview/run?restart=1").json()["status"], wait())
    time.sleep(1)
    out = subprocess.run(["ps", "-eo", "pid,ppid,stat,args", "--width", "1000"], capture_output=True, text=True).stdout
    lines = [l for l in out.splitlines() if pid in l or "defunct" in l]
    print("\n".join(lines) or "NO MATCHING PROCS")
    print("venv exists:", os.path.isdir(f"/tmp/donas_previews/{pid}/.venv"))
finally:
    print("delete", s.delete(f"{API}/projects/{pid}").status_code)
    time.sleep(1)
    out = subprocess.run(["ps", "-eo", "pid,stat,args", "--width", "1000"], capture_output=True, text=True).stdout
    print("after delete procs:", [l for l in out.splitlines() if pid in l], "dir:", os.path.exists(f"/tmp/donas_previews/{pid}"))
