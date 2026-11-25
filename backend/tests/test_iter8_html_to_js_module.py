# Iteration 8: html_to_js_module agent tool (TOOLS schema, dispatch, conversion, validation, options) + regression of file tools.
import asyncio, json, os, re, subprocess, sys
import pytest

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from agent import Agent, TOOLS, TOOL_NAMES  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")
LOOP = asyncio.new_event_loop()

HTML = ('<!DOCTYPE html><html><head><meta charset="utf-8"><title>Bling "Login" \u00e7</title>'
        '<link rel="stylesheet" href="https://cdn.ext-styles.com/bootstrap.css">'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Roboto">'
        '<script src="https://cdn.tracker.com/t.js"></script>'
        '<script src="js/local-old.js"></script>'
        '<script>window.x = "</div>"; console.log(\'old inline\');</script>'
        "<style>.a{content:'\\201C'}</style></head><body>\n"
        '<a href="https://ext.example.com/forgot">Esqueci</a> <a href="/local">Local</a>\n'
        '<img src="https://img.cdn.com/logo.png"> <p>Linha com `backtick` e ${tpl} e \\ barra</p>\n'
        + "<div>lorem ipsum</div>\n" * 3000 + "</body></html>")


def run(coro):
    return LOOP.run_until_complete(coro)


@pytest.fixture(scope="module")
def ctx(member):
    r = member.post(f"{BASE_URL}/api/projects", json={"name": "TEST_iter8_html2js"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    yield {"pid": pid, "s": member}
    member.delete(f"{BASE_URL}/api/projects/{pid}")


def agent(ctx):
    return Agent({"id": ctx["pid"]}, {"user_id": "unit"}, asyncio.Queue())


def files(ctx):
    return {f["path"]: f for f in ctx["s"].get(f"{BASE_URL}/api/projects/{ctx['pid']}").json()["files"]}


def decode(module):
    body = module[module.index("export default ") + len("export default "):].rstrip()
    assert body.endswith(";")
    return json.loads(body[:-1])


# Schema / registration
def test_tool_registered():
    t = next(t["function"] for t in TOOLS if t["function"]["name"] == "html_to_js_module")
    assert set(t["parameters"]["required"]) == {"html_path", "js_path"}
    assert "html_to_js_module" in TOOL_NAMES


class TestConvert:
    def test_setup_html(self, ctx):
        r = ctx["s"].put(f"{BASE_URL}/api/projects/{ctx['pid']}/files", json={"path": "frontend/public/bling_login.html", "content": HTML})
        assert r.status_code == 200, r.text

    def test_convert_default(self, ctx):
        a = agent(ctx)
        out = run(a.run_tool("html_to_js_module", {"html_path": "frontend/public/bling_login.html", "js_path": "frontend/src/bling_login_raw.js"}))
        assert out.startswith("OK"), out
        assert "import html from './bling_login_raw.js'" in out and "dangerouslySetInnerHTML" in out
        assert a.change_cards and a.change_cards[-1]["path"] == "frontend/src/bling_login_raw.js" and a.change_cards[-1]["op"] == "create"
        evts = []
        while not a.q.empty():
            evts.append(a.q.get_nowait())
        assert any(e["type"] == "change" for e in evts)
        m = files(ctx)["frontend/src/bling_login_raw.js"]["content"]
        assert m.startswith("//") and "\nexport default \"" in m
        html = decode(m)
        assert isinstance(html, str) and "lorem ipsum" in html and 'Bling "Login" \u00e7' in html
        assert "cdn.tracker.com" not in html
        assert 'href="#"' in html and "ext.example.com" not in html and 'href="/local"' in html
        assert "cdn.ext-styles.com" in html  # stylesheet kept by default
        assert "${tpl}" in html and "`backtick`" in html

    def test_no_script_tags(self, ctx):
        # spec: "cleans external links and old <script> tags" -> HTML must contain no <script> tags
        html = decode(files(ctx)["frontend/src/bling_login_raw.js"]["content"])
        assert not re.search(r"<script\b", html, re.I), "script tags left: " + str(re.findall(r"<script[^>]*>", html, re.I))

    def test_module_is_valid_js(self, ctx):
        m = files(ctx)["frontend/src/bling_login_raw.js"]["content"]
        p = "/tmp/iter8_mod.mjs"
        open(p, "w").write(m)
        r = subprocess.run(["node", "-e", f"import('{p}').then(m=>{{if(typeof m.default!=='string')process.exit(2);console.log(m.default.length)}})"],
                           capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr

    def test_overwrite_is_edit(self, ctx):
        a = agent(ctx)
        out = run(a.run_tool("html_to_js_module", {"html_path": "frontend/public/bling_login.html", "js_path": "frontend/src/bling_login_raw.js",
                                                    "keep_stylesheets": False}))
        assert out.startswith("OK"), out
        assert a.change_cards[-1]["op"] == "edit"
        html = decode(files(ctx)["frontend/src/bling_login_raw.js"]["content"])
        assert "cdn.ext-styles.com" not in html and "fonts.googleapis.com" not in html

    def test_keep_domains(self, ctx):
        out = run(agent(ctx).run_tool("html_to_js_module", {"html_path": "frontend/public/bling_login.html", "js_path": "frontend/src/k.js",
                                                             "keep_stylesheets": False, "keep_domains": ["googleapis.com", "ext.example.com"]}))
        assert out.startswith("OK"), out
        html = decode(files(ctx)["frontend/src/k.js"]["content"])
        assert "fonts.googleapis.com" in html and "https://ext.example.com/forgot" in html
        assert "cdn.ext-styles.com" not in html

    def test_source_untouched(self, ctx):
        assert files(ctx)["frontend/public/bling_login.html"]["content"] == HTML


class TestValidation:
    @pytest.mark.parametrize("js", ["frontend/public/x.js", "src/x.js", "frontend/src/../x.js"])
    def test_bad_dir(self, ctx, js):
        assert run(agent(ctx).run_tool("html_to_js_module", {"html_path": "frontend/public/bling_login.html", "js_path": js})).startswith("ERRO")

    def test_bad_ext(self, ctx):
        out = run(agent(ctx).run_tool("html_to_js_module", {"html_path": "frontend/public/bling_login.html", "js_path": "frontend/src/x.html"}))
        assert out.startswith("ERRO") and ".js" in out

    def test_missing_html(self, ctx):
        out = run(agent(ctx).run_tool("html_to_js_module", {"html_path": "frontend/public/nope.html", "js_path": "frontend/src/x.js"}))
        assert out.startswith("ERRO")

    def test_binary_html(self, ctx):
        r = ctx["s"].post(f"{BASE_URL}/api/projects/{ctx['pid']}/upload", data={"directory": "uploads"},
                          files=[("files", ("p.png", bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")))])
        assert r.status_code == 200
        out = run(agent(ctx).run_tool("html_to_js_module", {"html_path": "uploads/p.png", "js_path": "frontend/src/x.js"}))
        assert out.startswith("ERRO")

    def test_missing_args(self, ctx):
        assert run(agent(ctx).run_tool("html_to_js_module", {"html_path": "frontend/public/bling_login.html"})).startswith("ERRO")

    def test_no_file_created_on_error(self, ctx):
        assert "frontend/src/x.js" not in files(ctx)


# Regression: other file tools
class TestRegression:
    def test_other_tools(self, ctx):
        a = agent(ctx)
        assert run(a.run_tool("move_or_copy_file", {"source": "frontend/public/bling_login.html", "dest": "uploads/"})).startswith("OK")
        out = run(a.run_tool("clean_external_links", {"source": "uploads/bling_login.html", "dest": "uploads/clean.html"}))
        assert out.startswith("OK") and "ext.example.com" not in files(ctx)["uploads/clean.html"]["content"]
        out = run(a.run_tool("search_in_files", {"query": "export default", "path_glob": "frontend/src/*.js"}))
        assert "bling_login_raw.js:2:1" in out, out
