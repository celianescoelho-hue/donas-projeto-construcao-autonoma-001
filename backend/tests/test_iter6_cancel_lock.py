# Iteration 6: lock release on client disconnect, /cancel route, 409 guards (restore/import) while running, race 200/409.
# Uses ~5 short real OpenRouter runs. Creates a TEST_ project and deletes it at the end.
import json, os, subprocess, threading, time
import httpx, requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"


def tok(email):
    return subprocess.run(["python", "/app/backend/tests/clerk_token.py", email], capture_output=True, text=True).stdout.strip()


H = {"Authorization": f"Bearer {tok('forja.member+clerk_test@example.com')}"}
HA = {"Authorization": f"Bearer {tok('donas.admin+clerk_test@example.com')}"}
MODEL = "qwen/qwen3-coder-next"
LONG = "Escreva um texto de 400 palavras sobre a história do café. Não use ferramentas."
res = {}


def check(name, cond, info=""):
    res[name] = bool(cond)
    print(("PASS " if cond else "FAIL ") + name, str(info)[:300], flush=True)


def first_event(it):
    for line in it:
        if line.startswith("data:"):
            return json.loads(line[5:])


def short_chat(pid, prompt="Responda apenas 'ok'. Não use ferramentas."):
    with httpx.Client(timeout=200) as c, c.stream("POST", f"{API}/projects/{pid}/chat", json={"prompt": prompt, "model": MODEL}, headers=H) as r:
        if r.status_code != 200:
            r.read()
            return r.status_code, r.text[:200]
        evs = [json.loads(l[5:]) for l in r.iter_lines() if l.startswith("data:")]
        return 200, [e["type"] for e in evs if e["type"] != "token"]


pid = requests.post(f"{API}/projects", json={"name": "TEST_iter6_locks"}, headers=H).json()["id"]
print("pid", pid)
try:
    # 1) cancel idle
    r = requests.post(f"{API}/projects/{pid}/cancel", headers=H)
    check("cancel_idle", r.status_code == 200 and r.json() == {"ok": True, "was_running": False}, r.text)
    # ownership: other user -> 403/404 ; no auth -> 401/403
    r = requests.post(f"{API}/projects/{pid}/cancel", headers=HA)
    check("cancel_other_user_denied", r.status_code in (403, 404), (r.status_code, r.text[:120]))
    r = requests.post(f"{API}/projects/{pid}/cancel")
    check("cancel_no_auth_denied", r.status_code in (401, 403), r.status_code)
    r = requests.post(f"{API}/projects/does-not-exist/cancel", headers=H)
    check("cancel_unknown_404", r.status_code == 404, r.status_code)

    # 2) disconnect mid-stream -> lock released
    c = httpx.Client(timeout=60)
    cm = c.stream("POST", f"{API}/projects/{pid}/chat", json={"prompt": LONG, "model": MODEL}, headers=H)
    r = cm.__enter__()
    check("disconnect_chat_200", r.status_code == 200, r.status_code)
    ev = first_event(r.iter_lines())
    check("first_event_start", ev and ev.get("type") == "start", ev)
    time.sleep(2)
    cm.__exit__(None, None, None)
    c.close()
    t0 = time.time()
    time.sleep(2)
    code, info = short_chat(pid)
    check("chat_after_disconnect_200", code == 200 and "done" in info, (code, info, round(time.time() - t0, 1)))
    msgs = requests.get(f"{API}/projects/{pid}/messages", headers=H).json()
    errs = [m.get("error") for m in msgs if m["role"] == "assistant"]
    check("disconnect_saved_interrompida", any((e or "").startswith("Execução interrompida") for e in errs), errs)

    requests.put(f"{API}/projects/{pid}/files", json={"path": "a.txt", "content": "x"}, headers=H)
    # 3) /cancel while stream open -> was_running true, new chat 200, first stream ends
    c = httpx.Client(timeout=60)
    cm = c.stream("POST", f"{API}/projects/{pid}/chat", json={"prompt": LONG, "model": MODEL}, headers=H)
    r = cm.__enter__()
    it = r.iter_lines()
    first_event(it)
    # while truly running: restore(before) and import must be 409
    vers = requests.get(f"{API}/projects/{pid}/versions", headers=H).json()
    if vers:
        rr = requests.post(f"{API}/projects/{pid}/versions/{vers[0]['id']}/restore?mode=before", headers=H)
        check("restore_while_running_409", rr.status_code == 409, (rr.status_code, rr.text[:120]))
    else:
        print("SKIP restore_while_running_409 (no versions)")
    ri = requests.post(f"{API}/projects/{pid}/github/import", json={"owner": "octocat", "repo": "Hello-World", "branch": "master"}, headers=H)
    check("import_while_running_409", ri.status_code == 409 and "ocupado" in ri.text, (ri.status_code, ri.text[:120]))
    rc = requests.post(f"{API}/projects/{pid}/cancel", headers=H)
    check("cancel_running", rc.status_code == 200 and rc.json().get("was_running") is True, rc.text)
    ended = {"v": False, "types": []}

    def drain():
        try:
            for l in it:
                if l.startswith("data:"):
                    ended["types"].append(json.loads(l[5:])["type"])
            ended["v"] = True
        except Exception as e:
            ended["v"] = f"exc {e}"
    th = threading.Thread(target=drain); th.start(); th.join(15)
    check("first_stream_ends_after_cancel", ended["v"] is True, [t for t in ended["types"] if t != "token"][-4:])
    cm.__exit__(None, None, None); c.close()
    code, info = short_chat(pid)
    check("chat_after_cancel_200", code == 200, (code, info))
    rc = requests.post(f"{API}/projects/{pid}/cancel", headers=H)
    check("cancel_idle_after", rc.json().get("was_running") is False, rc.text)

    # 4) race -> one 200 one 409
    barrier = threading.Barrier(2)
    out = [None, None]

    def go(i):
        barrier.wait()
        out[i] = short_chat(pid)
    ths = [threading.Thread(target=go, args=(i,)) for i in range(2)]
    [t.start() for t in ths]; [t.join() for t in ths]
    check("race_200_409", sorted(o[0] for o in out) == [200, 409], out)
finally:
    print("delete", requests.delete(f"{API}/projects/{pid}", headers=H).status_code)
    print("SUMMARY", sum(res.values()), "/", len(res))
