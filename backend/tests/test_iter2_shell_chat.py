# Iteration 2: one real chat (qwen3-coder-next) asking for a shell command; also checks 409 on concurrent chat
import json, os, subprocess, sys, time, threading
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
tok = subprocess.run(["python", "/app/backend/tests/clerk_token.py", "forja.member+clerk_test@example.com"],
                     capture_output=True, text=True).stdout.strip()
s = requests.Session(); s.headers["Authorization"] = f"Bearer {tok}"
pid = s.post(f"{API}/projects", json={"name": "TEST_shell_chat"}).json()["id"]
s.put(f"{API}/projects/{pid}/files", json={"path": "frontend/package.json", "content": '{"name":"x","dependencies":{"react":"18"}}'})
print("pid", pid)
t0 = time.time()
events = []
second = {}
try:
    with s.post(f"{API}/projects/{pid}/chat", json={"prompt": "Rode npm install e depois liste os arquivos", "model": "qwen/qwen3-coder-next"},
                stream=True, timeout=200) as r:
        print("status", r.status_code)
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            ev = json.loads(line[5:])
            if ev["type"] == "start" and not second:
                r2 = s.post(f"{API}/projects/{pid}/chat", json={"prompt": "oi"}, timeout=30)
                second = {"code": r2.status_code, "body": r2.text[:200]}
                print("second chat:", second)
            if ev["type"] != "token":
                print(round(time.time() - t0, 1), {k: (v if k != "message" else (v if isinstance(v, str) else v.get("content", "")[:600])) for k, v in ev.items()})
            events.append(ev)
    print("elapsed", round(time.time() - t0, 1))
    tools = [e["name"] for e in events if e["type"] == "tool"]
    print("tools called:", tools)
    print("tool_errors:", [e for e in events if e["type"] == "tool_error"])
    print("done:", any(e["type"] == "done" for e in events))
    msgs = s.get(f"{API}/projects/{pid}/messages").json()
    print("messages:", [(m["role"], m["content"][:300]) for m in msgs])
finally:
    print("delete", s.delete(f"{API}/projects/{pid}").status_code)
