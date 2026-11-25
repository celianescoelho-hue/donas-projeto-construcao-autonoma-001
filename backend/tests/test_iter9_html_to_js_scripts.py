# Iteration 9: html_to_js_module must strip ALL <script> tags (external, local, inline) + edge cases.
import asyncio, json, os, re, subprocess, sys
import pytest

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from agent import Agent, ALL_SCRIPT  # noqa: E402

BASE_URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")
LOOP = asyncio.new_event_loop()

BASIC = ('<html><head><script src="https://cdn.tracker.com/t.js"></script>'
         "<script src='js/local.js'></script><script>var a=1</script></head>"
         '<body><a href="https://x.com/a">x</a><p>ok</p></body></html>')

EDGE = ('<html><head><SCRIPT TYPE="text/javascript">var b = "<div>";</SCRIPT>'
        '<script type="module">\nimport x from "./y.js";\nif (1 < 2) {}\n</script>'
        '<script>var z=1</script >'
        '<Script src="//cdn.other.com/a.js" async></Script>'
        '<script type="application/ld+json">{"a":"</div>"}</script></head>'
        '<body><p>keep me</p><noscript>ns</noscript></body></html>')


def run(c):
    return LOOP.run_until_complete(c)


@pytest.fixture(scope="module")
def ctx(member):
    r = member.post(f"{BASE_URL}/api/projects", json={"name": "TEST_iter9_html2js"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    for p, c in (("frontend/public/basic.html", BASIC), ("frontend/public/edge.html", EDGE)):
        assert member.put(f"{BASE_URL}/api/projects/{pid}/files", json={"path": p, "content": c}).status_code == 200
    yield {"pid": pid, "s": member}
    member.delete(f"{BASE_URL}/api/projects/{pid}")


def agent(ctx):
    return Agent({"id": ctx["pid"]}, {"user_id": "unit"}, asyncio.Queue())


def files(ctx):
    return {f["path"]: f for f in ctx["s"].get(f"{BASE_URL}/api/projects/{ctx['pid']}").json()["files"]}


def decode(m):
    body = m[m.index("export default ") + 15:].rstrip()
    assert body.endswith(";")
    return json.loads(body[:-1])


def node_ok(m, name):
    p = f"/tmp/{name}.mjs"
    open(p, "w").write(m)
    r = subprocess.run(["node", "-e", f"import('{p}').then(m=>{{if(typeof m.default!=='string')process.exit(2)}})"], capture_output=True, text=True, timeout=30)
    return r.returncode == 0, r.stderr


class TestScripts:
    def test_basic_all_removed(self, ctx):
        a = agent(ctx)
        out = run(a.run_tool("html_to_js_module", {"html_path": "frontend/public/basic.html", "js_path": "frontend/src/basic.js"}))
        print("MSG:", out)
        print("CARD:", a.change_cards[-1].get("summary") if a.change_cards else None)
        assert out.startswith("OK"), out
        m = files(ctx)["frontend/src/basic.js"]["content"]
        assert m.startswith("//") and "\nexport default \"" in m
        html = decode(m)
        assert html.lower().count("<script") == 0, html
        assert "<p>ok</p>" in html and 'href="#"' in html
        assert re.search(r"\d+ <script> removidos", out)
        ok, err = node_ok(m, "iter9_basic")
        assert ok, err
        assert a.change_cards and a.change_cards[-1]["path"] == "frontend/src/basic.js"

    def test_reported_count_matches_total(self, ctx):
        # 3 script tags in source (1 external + 1 local + 1 inline)
        out = run(agent(ctx).run_tool("html_to_js_module", {"html_path": "frontend/public/basic.html", "js_path": "frontend/src/basic.js"}))
        n = int(re.search(r"(\d+) <script> removidos", out).group(1))
        assert n == 3, f"message reports {n} scripts removed, source has 3: {out}"

    def test_edge_cases(self, ctx):
        out = run(agent(ctx).run_tool("html_to_js_module", {"html_path": "frontend/public/edge.html", "js_path": "frontend/src/edge.js"}))
        print("EDGE MSG:", out)
        assert out.startswith("OK"), out
        m = files(ctx)["frontend/src/edge.js"]["content"]
        html = decode(m)
        print("EDGE HTML:", html)
        assert "<p>keep me</p>" in html and "<noscript>ns</noscript>" in html
        assert html.lower().count("<script") == 0, html
        ok, err = node_ok(m, "iter9_edge")
        assert ok, err

    def test_unclosed_script_perf(self):
        import time
        big = "<script>" + "<div>x</div>" * 50000
        t = time.time()
        ALL_SCRIPT.sub("", big)
        assert time.time() - t < 2
