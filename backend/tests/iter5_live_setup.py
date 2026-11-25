# Iteration 5 helper: create/delete a TEST_ public project copied from 90476221 text files (for live-poll UI test)
import sys, os, subprocess, requests
from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")
B = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
tok = subprocess.run(["python", "/app/backend/tests/clerk_token.py", "forja.member+clerk_test@example.com"], capture_output=True, text=True).stdout.strip()
s = requests.Session(); s.headers["Authorization"] = f"Bearer {tok}"
cmd = sys.argv[1]
if cmd == "create":
    src = s.get(f"{B}/api/projects/90476221-f03b-4fd0-b84e-113bfdfcedbc").json()["files"]
    pid = s.post(f"{B}/api/projects", json={"name": "TEST_live_poll"}).json()["id"]
    for f in src:
        if f["kind"] == "text":
            s.put(f"{B}/api/projects/{pid}/files", json={"path": f["path"], "content": f["content"]})
    s.patch(f"{B}/api/projects/{pid}", json={"public_preview": True})
    print(pid)
elif cmd == "edit":
    pid, path = sys.argv[2], sys.argv[3]
    c = next(f for f in s.get(f"{B}/api/projects/{pid}").json()["files"] if f["path"] == path)["content"]
    new = c.replace("Olá Forja", "Olá Atualizado")
    print(s.put(f"{B}/api/projects/{pid}/files", json={"path": path, "content": new}).json(), "changed" if new != c else "NOCHANGE")
elif cmd == "show":
    for f in s.get(f"{B}/api/projects/{sys.argv[2]}").json()["files"]:
        if "Forja" in (f["content"] or ""):
            print(f["path"])
elif cmd == "public":
    print(s.patch(f"{B}/api/projects/{sys.argv[2]}", json={"public_preview": sys.argv[3] == "on"}).json().get("public_preview"))
elif cmd == "delete":
    print(s.delete(f"{B}/api/projects/{sys.argv[2]}").json())
