# Creates scratch projects for iteration 4 UI tests (preview error + env injection). Prints ids.
import os, subprocess, sys, requests, json
BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")
tok = subprocess.run(["python", "/app/backend/tests/clerk_token.py", "forja.member+clerk_test@example.com"], capture_output=True, text=True).stdout.strip()
s = requests.Session(); s.headers["Authorization"] = f"Bearer {tok}"
if len(sys.argv) > 1 and sys.argv[1] == "delete":
    for pid in sys.argv[2:]:
        print(pid, s.delete(f"{BASE}/api/projects/{pid}").status_code)
    sys.exit()
IDX = "import React from 'react';\nimport { createRoot } from 'react-dom/client';\nimport App from './App';\ncreateRoot(document.getElementById('root')).render(<App />);\n"
PKG = '{"name":"x","dependencies":{"react":"18.2.0","react-dom":"18.2.0"}}'
out = {}
for name, app in [("TEST_iter4_err", "export default function App(){ throw new Error('boom teste'); }\n"),
                  ("TEST_iter4_env", "export default function App(){\n  return <h1 id=\"t\">Titulo: {process.env.REACT_APP_TITLE}</h1>;\n}\n")]:
    pid = s.post(f"{BASE}/api/projects", json={"name": name}).json()["id"]
    for p, c in [("frontend/package.json", PKG), ("frontend/src/index.js", IDX), ("frontend/src/App.js", app)]:
        assert s.put(f"{BASE}/api/projects/{pid}/files", json={"path": p, "content": c}).status_code == 200
    out[name] = pid
print(json.dumps(out))
