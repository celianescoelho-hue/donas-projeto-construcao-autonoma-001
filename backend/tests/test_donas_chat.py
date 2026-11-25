# Donas agent chat SSE test (costs real OpenRouter credit: ONE call). Run: pytest -n 0 tests/test_donas_chat.py -s
import json
import time
from conftest import BASE_URL

API = f"{BASE_URL}/api"
HERO = """export default function Hero() {
  return (
    <section className="hero">
      <h1>Olá Mundo</h1>
      <p>Subtítulo do site</p>
    </section>
  );
}
"""


def test_chat_replace_in_file(member, created_projects):
    pid = member.post(f"{API}/projects", json={"name": "TEST_chat"}).json()["id"]
    created_projects.append(pid)
    assert member.put(f"{API}/projects/{pid}/files", json={"path": "frontend/src/components/Hero.jsx", "content": HERO}).status_code == 200
    t0 = time.time()
    r = member.post(f"{API}/projects/{pid}/chat", json={"prompt": "Mude o título do Hero para Bem-vindo. Só isso."}, stream=True, timeout=300)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    events = []
    for line in r.iter_lines(decode_unicode=True):
        if line and line.startswith("data:"):
            ev = json.loads(line[5:])
            events.append(ev)
            if ev["type"] != "token":
                print(round(time.time() - t0, 1), ev["type"], {k: v for k, v in ev.items() if k in ("name", "path", "added", "removed", "message", "model", "key_source")} if ev["type"] != "done" else "")
            if ev["type"] == "done":
                break
    types = [e["type"] for e in events]
    assert types[0] == "start" and events[0]["model"] == "qwen/qwen3-coder-next"
    assert "tool" in types and "change" in types and types[-1] == "done"
    done = events[-1]["message"]
    print("assistant:", done["content"][:300], "cost", done["cost"], "tokens", done["tokens"], "version", done["version"], "error", done["error"])
    assert done["error"] is None
    assert done["version"] and done["version"]["number"] == 2
    assert done["changes"] and done["changes"][0]["path"] == "frontend/src/components/Hero.jsx"
    files = {f["path"]: f for f in member.get(f"{API}/projects/{pid}").json()["files"]}
    assert "Bem-vindo" in files["frontend/src/components/Hero.jsx"]["content"]
    vs = member.get(f"{API}/projects/{pid}/versions").json()
    assert vs[0]["source"] == "ai"
    msgs = member.get(f"{API}/projects/{pid}/messages").json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert done["cost"] > 0, "usage cost not recorded"
