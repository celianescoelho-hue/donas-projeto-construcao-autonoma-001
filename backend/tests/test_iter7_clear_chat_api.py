# Iteration 7 API checks: DELETE /projects/{pid}/messages (soft delete, 409 while running, ownership),
# files/versions untouched, and one real OpenRouter change run on a project with polluted fake history.
# Uses exactly 2 real OpenRouter runs. Creates a TEST_ project and deletes it at the end.
import asyncio, json, os, subprocess, time
import httpx, requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
MODEL = "qwen/qwen3-coder-next"
res = {}


def tok(email):
    return subprocess.run(["python", "/app/backend/tests/clerk_token.py", email], capture_output=True, text=True).stdout.strip()


H = {"Authorization": f"Bearer {tok('forja.member+clerk_test@example.com')}"}
HA = {"Authorization": f"Bearer {tok('donas.admin+clerk_test@example.com')}"}


def check(name, cond, info=""):
    res[name] = bool(cond)
    print(("PASS " if cond else "FAIL ") + name, str(info)[:400], flush=True)


def snapshot(pid):
    p = requests.get(f"{API}/projects/{pid}", headers=H).json()
    v = requests.get(f"{API}/projects/{pid}/versions", headers=H).json()
    files = sorted((f["path"], f.get("size")) for f in p["files"])
    return files, [x.get("id") for x in (v if isinstance(v, list) else v.get("versions", []))], p["project"]


async def seed_fake_history(pid):
    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    docs = []
    for i in range(10):
        role = "user" if i % 2 == 0 else "assistant"
        content = f"Pedido antigo {i}: mude algo" if role == "user" else \
            f"Arquivo criado: frontend/src/pages/Old{i}.jsx\n0 arquivo(s)\n[Alterações: frontend/src/pages/Old{i}.jsx (+3/-1)]"
        docs.append({"id": f"TEST_seed_{pid}_{i}", "project_id": pid, "role": role, "content": content,
                     "changes": [], "created_at": f"2025-12-01T00:00:{i:02d}+00:00"})
    await db.messages.insert_many(docs)
    n = await db.messages.count_documents({"project_id": pid, "archived": True})
    return n


pid = requests.post(f"{API}/projects", json={"name": "TEST_iter7_clear_chat"}, headers=H).json()["id"]
print("pid", pid)
try:
    home = "export default function Home() {\n  return (\n    <div>\n      <h1>Minha Loja</h1>\n      <p>Olá</p>\n    </div>\n  );\n}\n"
    app = "import Home from './pages/Home';\nexport default function App(){ return <Home/>; }\n"
    for path, c in [("frontend/src/pages/Home.jsx", home), ("frontend/src/App.js", app)]:
        r = requests.put(f"{API}/projects/{pid}/files", json={"path": path, "content": c}, headers=H)
        assert r.status_code == 200, r.text
    asyncio.run(seed_fake_history(pid))
    msgs = requests.get(f"{API}/projects/{pid}/messages", headers=H).json()
    check("seeded_10_messages", len(msgs) == 10, len(msgs))

    # ownership / auth
    r = requests.delete(f"{API}/projects/{pid}/messages", headers=HA)
    check("clear_other_user_404", r.status_code in (403, 404), (r.status_code, r.text[:100]))
    r = requests.delete(f"{API}/projects/{pid}/messages")
    check("clear_no_auth_denied", r.status_code in (401, 403), r.status_code)
    check("other_user_did_not_clear", len(requests.get(f"{API}/projects/{pid}/messages", headers=H).json()) == 10)

    # REAL RUN 1: real change on polluted history
    t0 = time.time()
    events = []
    with httpx.Client(timeout=400) as c, c.stream("POST", f"{API}/projects/{pid}/chat",
                                                  json={"prompt": "Mude o título do Home para Bem-vindo", "model": MODEL}, headers=H) as r:
        check("real_chat_200", r.status_code == 200, r.status_code)
        for line in r.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
    done = next((e for e in events if e["type"] == "done"), None)
    tools = [(e["name"], e.get("path")) for e in events if e["type"] == "tool"]
    warns = [e["message"] for e in events if e["type"] == "warning"]
    print("elapsed", round(time.time() - t0, 1), "tools", tools, "warnings", warns)
    m = done and done["message"]
    print("final text:", m and m["content"][:500], "changes:", m and [c_["path"] for c_ in m["changes"]], "error:", m and m.get("error"))
    check("real_changes_gt_0", m and len(m["changes"]) > 0)
    home_now = next(f for f in requests.get(f"{API}/projects/{pid}", headers=H).json()["files"] if f["path"] == "frontend/src/pages/Home.jsx")
    full = requests.get(f"{API}/projects/{pid}", headers=H).json()
    hc = next((f.get("content") for f in full["files"] if f["path"] == "frontend/src/pages/Home.jsx"), None)
    check("home_title_changed", hc is not None and "Bem-vindo" in hc, (hc or "")[:200])
    check("no_fake_summary_left", m and "[Alterações" not in m["content"] and "0 arquivo(s)" not in m["content"], m and m["content"][:200])

    # REAL RUN 2: start long run, DELETE must 409, then cancel
    before_files, before_versions, before_proj = snapshot(pid)
    c = httpx.Client(timeout=120)
    cm = c.stream("POST", f"{API}/projects/{pid}/chat",
                  json={"prompt": "Escreva um texto de 400 palavras sobre a história do café. Não use ferramentas.", "model": MODEL}, headers=H)
    r = cm.__enter__()
    check("long_chat_200", r.status_code == 200, r.status_code)
    it = r.iter_lines()
    for line in it:
        if line.startswith("data:"):
            break
    r409 = requests.delete(f"{API}/projects/{pid}/messages", headers=H)
    check("clear_while_running_409", r409.status_code == 409, (r409.status_code, r409.text[:150]))
    rc = requests.post(f"{API}/projects/{pid}/cancel", headers=H)
    check("cancel_ok", rc.status_code == 200 and rc.json().get("was_running") is True, rc.text)
    try:
        cm.__exit__(None, None, None)
    except Exception:
        pass
    c.close()
    time.sleep(3)

    # clear
    before_files, before_versions, before_proj = snapshot(pid)
    n_before = len(requests.get(f"{API}/projects/{pid}/messages", headers=H).json())
    r = requests.delete(f"{API}/projects/{pid}/messages", headers=H)
    check("clear_200", r.status_code == 200 and r.json().get("ok") is True and r.json().get("deleted") == n_before, (r.text, n_before))
    check("messages_empty_after", requests.get(f"{API}/projects/{pid}/messages", headers=H).json() == [])
    after_files, after_versions, after_proj = snapshot(pid)
    check("files_untouched", before_files == after_files, (before_files, after_files))
    check("versions_untouched", before_versions == after_versions and len(after_versions) > 0, (len(before_versions), len(after_versions)))
    check("project_untouched", before_proj.get("name") == after_proj.get("name") and before_proj.get("id") == after_proj.get("id"))
    r = requests.delete(f"{API}/projects/{pid}/messages", headers=H)
    check("clear_again_deleted_0", r.status_code == 200 and r.json().get("deleted") == 0, r.text)

    async def archived_count():
        from motor.motor_asyncio import AsyncIOMotorClient
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        return await db.messages.count_documents({"project_id": pid, "archived": True}), \
            await db.messages.count_documents({"project_id": pid, "archived": True, "archived_at": {"$exists": True}})
    a, b = asyncio.run(archived_count())
    check("soft_deleted_archived_true", a == n_before and b == n_before, (a, b, n_before))
    r = requests.delete(f"{API}/projects/does-not-exist/messages", headers=H)
    check("clear_unknown_404", r.status_code == 404, r.status_code)
finally:
    requests.delete(f"{API}/projects/{pid}", headers=H)
    print("deleted project", pid)
print(f"RESULT {sum(res.values())}/{len(res)}")
