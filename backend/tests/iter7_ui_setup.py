# Iteration 7 helper: create/delete a TEST_ scratch project with 2 files + 6 seeded chat messages (for clear-chat UI test)
import sys, os, subprocess, asyncio, requests
from dotenv import load_dotenv
load_dotenv("/app/frontend/.env"); load_dotenv("/app/backend/.env")
B = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
tok = subprocess.run(["python", "/app/backend/tests/clerk_token.py", "forja.member+clerk_test@example.com"], capture_output=True, text=True).stdout.strip()
s = requests.Session(); s.headers["Authorization"] = f"Bearer {tok}"
cmd = sys.argv[1]


async def seed(pid):
    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    await db.messages.insert_many([{"id": f"TEST_ui_{pid}_{i}", "project_id": pid, "role": "user" if i % 2 == 0 else "assistant",
                                    "content": f"TEST mensagem {i}", "changes": [], "created_at": f"2025-12-01T00:00:{i:02d}+00:00"} for i in range(6)])

if cmd == "create":
    pid = s.post(f"{B}/api/projects", json={"name": "TEST_iter7_ui_clear"}).json()["id"]
    s.put(f"{B}/api/projects/{pid}/files", json={"path": "frontend/src/App.js", "content": "export default function App(){return <h1>Oi</h1>}\n"})
    s.put(f"{B}/api/projects/{pid}/files", json={"path": "frontend/src/index.js", "content": "import App from './App';\n"})
    asyncio.run(seed(pid))
    print(pid)
elif cmd == "ticket":
    print(subprocess.run(["python", "/app/backend/tests/clerk_token.py", "forja.member+clerk_test@example.com", "ticket"], capture_output=True, text=True).stdout.strip())
elif cmd == "delete":
    print(s.delete(f"{B}/api/projects/{sys.argv[2]}").json())
