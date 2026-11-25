# Iteration 6: real model check - Qwen3 Coder Next must call search_in_files with a non-empty query (1 run)
import json, os, subprocess
import httpx
from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
H = {"Authorization": "Bearer " + subprocess.run(["python", "/app/backend/tests/clerk_token.py", "forja.member+clerk_test@example.com"], capture_output=True, text=True).stdout.strip()}
PID = "90476221-f03b-4fd0-b84e-113bfdfcedbc"
with httpx.Client(timeout=300) as c, c.stream("POST", f"{API}/projects/{PID}/chat", headers=H, json={
        "prompt": "Procure onde está o texto Cliques e me diga o arquivo e a linha, sem alterar nada", "model": "qwen/qwen3-coder-next"}) as r:
    print("status", r.status_code)
    for l in r.iter_lines():
        if not l.startswith("data:"):
            continue
        e = json.loads(l[5:])
        if e["type"] in ("tool", "tool_error", "error", "warning"):
            print("EV", json.dumps(e, ensure_ascii=False)[:400])
        elif e["type"] == "done":
            m = e["message"]
            print("DONE error=", m.get("error"), "changes=", len(m.get("changes") or []))
            print("TEXT", m["content"][:800])
