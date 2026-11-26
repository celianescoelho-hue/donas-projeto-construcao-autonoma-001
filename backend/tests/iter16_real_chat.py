# Iteration 16: one real chat asking create_file overwrite of a 120-line file. Usage: python iter16_real_chat.py <pid>
import sys, json, subprocess, requests, os
from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
tok = subprocess.run(["python", "/app/backend/tests/clerk_token.py", "forja.member+clerk_test@example.com"], capture_output=True, text=True).stdout.strip()
s = requests.Session(); s.headers["Authorization"] = "Bearer " + tok
pid = sys.argv[1]
s.put(f"{API}/projects/{pid}/files", json={"path": "notes.txt", "content": "\n".join(f"nota antiga {i}" for i in range(120))})
r = s.post(f"{API}/projects/{pid}/chat", json={"prompt": "Reescreva o arquivo notes.txt inteiro usando create_file (uma única chamada, sem ler antes) com exatamente este texto de 3 linhas:\nALFA\nBETA\nGAMA"}, stream=True, timeout=200)
print("status", r.status_code)
for line in r.iter_lines(decode_unicode=True):
    if line and line.startswith("data:"):
        ev = json.loads(line[5:])
        if ev["type"] == "token": continue
        if ev["type"] == "done":
            m = ev["message"]; print("DONE model", m["model"], "changes", [(c["path"], c["op"]) for c in m["changes"]], "error", m["error"], "cost", m["cost"])
        else: print(ev)
files = s.get(f"{API}/projects/{pid}").json()["files"]
print("notes.txt:", repr(next(f for f in files if f["path"] == "notes.txt")["content"][:100]))
