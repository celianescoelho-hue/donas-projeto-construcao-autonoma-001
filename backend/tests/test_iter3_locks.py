# Iteration 3: RUNNING lock checks (chat race 200/409, import lock release, import 409 on non-empty). Uses 2 real model runs.
import json, os, subprocess, threading, time
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
tok = subprocess.run(["python", "/app/backend/tests/clerk_token.py", "forja.member+clerk_test@example.com"],
                     capture_output=True, text=True).stdout.strip()
H = {"Authorization": f"Bearer {tok}"}
results = {}


def check(name, cond, info=""):
    results[name] = bool(cond)
    print(("PASS " if cond else "FAIL ") + name, info)


def drain(r):
    evs = []
    for line in r.iter_lines(decode_unicode=True):
        if line and line.startswith("data:"):
            evs.append(json.loads(line[5:]))
    return evs


pid = requests.post(f"{API}/projects", json={"name": "TEST_iter3_locks"}, headers=H).json()["id"]
print("pid", pid)
IMP = {"owner": "octocat", "repo": "Hello-World", "branch": "master"}
try:
    # Import without PAT -> 400, twice (lock released)
    r1 = requests.post(f"{API}/projects/{pid}/github/import", json=IMP, headers=H)
    check("import_no_pat_400", r1.status_code == 400 and "Conecte o GitHub" in r1.text, (r1.status_code, r1.text[:150]))
    r1b = requests.post(f"{API}/projects/{pid}/github/import", json=IMP, headers=H)
    check("import_again_not_409", r1b.status_code == 400, (r1b.status_code, r1b.text[:100]))

    # Parallel chats -> exactly one 200 and one 409
    barrier = threading.Barrier(2)
    out = [None, None]

    def go(i):
        barrier.wait()
        r = requests.post(f"{API}/projects/{pid}/chat", json={"prompt": "Responda apenas 'ok'. Não use ferramentas.",
                          "model": "qwen/qwen3-coder-next"}, headers=H, stream=True, timeout=200)
        if r.status_code == 200:
            evs = drain(r)
            out[i] = (200, [e["type"] for e in evs if e["type"] != "token"])
        else:
            out[i] = (r.status_code, r.text[:150])

    ths = [threading.Thread(target=go, args=(i,)) for i in range(2)]
    t0 = time.time()
    [t.start() for t in ths]
    [t.join() for t in ths]
    codes = sorted(o[0] for o in out)
    check("parallel_chat_200_409", codes == [200, 409], out)
    print("race elapsed", round(time.time() - t0, 1))
    time.sleep(1)

    # New chat after finish -> 200; during it, import -> 409 busy
    with requests.post(f"{API}/projects/{pid}/chat", json={"prompt": "Responda apenas 'ok'.", "model": "qwen/qwen3-coder-next"},
                       headers=H, stream=True, timeout=200) as r:
        check("chat_after_race_200", r.status_code == 200, r.status_code)
        if r.status_code == 200:
            ri = requests.post(f"{API}/projects/{pid}/github/import", json=IMP, headers=H)
            check("import_while_chat_409", ri.status_code == 409, (ri.status_code, ri.text[:150]))
            evs = drain(r)
            check("second_chat_done", any(e["type"] == "done" for e in evs), [e["type"] for e in evs if e["type"] != "token"][-5:])
    time.sleep(1)

    # Project with files -> 409
    requests.put(f"{API}/projects/{pid}/files", json={"path": "a.txt", "content": "x"}, headers=H)
    r3 = requests.post(f"{API}/projects/{pid}/github/import", json=IMP, headers=H)
    check("import_with_files_409", r3.status_code == 409 and "arquivos" in r3.text, (r3.status_code, r3.text[:150]))
    r4 = requests.post(f"{API}/projects/{pid}/github/import", json=IMP, headers=H)
    check("import_with_files_409_again", r4.status_code == 409 and "arquivos" in r4.text, r4.status_code)
finally:
    print("delete", requests.delete(f"{API}/projects/{pid}", headers=H).status_code)
    print("SUMMARY", sum(results.values()), "/", len(results))
