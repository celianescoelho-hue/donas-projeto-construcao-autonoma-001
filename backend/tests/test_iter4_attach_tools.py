# Iteration 4: attachments upload (pdf/zip/10MB), server tools (move/copy, clean links, extract zip, read_file budget, pdf),
# search_in_files, empty-response error, env manager, versions restore before/after.
import asyncio, io, os, re, sys, zipfile
import pytest
import requests

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from agent import Agent  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")
LOOP = asyncio.new_event_loop()


def run(coro):
    return LOOP.run_until_complete(coro)


def make_pdf(texts):
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for t in texts:
        stream = f"BT /F1 18 Tf 50 700 Td ({t}) Tj ET"
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
        cid = len(objs)
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {cid} 0 R >>")
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    x = len(out)
    out += f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    out += f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()
    return out


def make_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("site/index.html", "<h1>oi</h1>")
        z.writestr("site/style.css", "body{color:red}")
        z.writestr("site/data.json", '{"a":1}')
    return buf.getvalue()


def make_big_html():
    head = ('<!DOCTYPE html><html><head><meta charset="utf-8">'
            '<link rel="preconnect" href="https://fonts.gstatic.com">'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Roboto">'
            '<link rel="stylesheet" href="local.css">'
            '<script src="https://cdn.tracker.com/t.js"></script>'
            '<script src="app.js"></script><style>.x{color:#123}</style></head><body>\n')
    block = ('<div class="card" data-k="v"><a href="https://evil.com/page?x=1">Ext</a> <a href="/local/page">Loc</a> '
             '<img src="https://img.cdn.com/a.png" alt="a"> <img src="img/local.png"> '
             '<img srcset="https://img.cdn.com/a1.png 1x, https://img.cdn.com/a2.png 2x"> '
             '<iframe src="https://www.youtube.com/embed/x"></iframe><p>Texto ' + "lorem ipsum " * 20 + '</p></div>\n')
    return head + block * 270 + "</body></html>"


@pytest.fixture(scope="module")
def ctx(member):
    r = member.post(f"{BASE_URL}/api/projects", json={"name": "TEST_iter4_tools"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    yield {"pid": pid, "s": member}
    member.delete(f"{BASE_URL}/api/projects/{pid}")


def agent(ctx):
    return Agent({"id": ctx["pid"]}, {"user_id": "unit"}, asyncio.Queue())


def upload(ctx, name, data, directory="uploads"):
    return ctx["s"].post(f"{BASE_URL}/api/projects/{ctx['pid']}/upload", files=[("files", (name, data))], data={"directory": directory})


class TestUpload:
    def test_pdf_zip_html_upload(self, ctx):
        r = upload(ctx, "doc.pdf", make_pdf(["Pagina um Donas", "Pagina dois"]))
        assert r.status_code == 200, r.text
        j = r.json()
        assert not j["errors"], j
        assert j["saved"][0]["path"] == "uploads/doc.pdf"
        assert "2 páginas" in j["saved"][0]["summary"], j["saved"][0]["summary"]
        r = upload(ctx, "site.zip", make_zip())
        s = r.json()["saved"][0]
        assert "ZIP com 3 arquivos" in s["summary"], s
        html = make_big_html()
        r = upload(ctx, "page.html", html.encode())
        assert r.json()["saved"][0]["path"] == "uploads/page.html"
        assert len(html) > 140000

    def test_10mb_limit_and_unsupported(self, ctx):
        r = upload(ctx, "big.txt", b"a" * (10 * 1024 * 1024 + 10))
        assert r.status_code == 200
        assert any("10 MB" in e for e in r.json()["errors"])
        r = upload(ctx, "x.exe", b"MZ")
        assert any("não suportado" in e for e in r.json()["errors"])


class TestServerTools:
    def test_read_pdf(self, ctx):
        out = run(agent(ctx).run_tool("read_file", {"path": "uploads/doc.pdf"}))
        assert "página 1" in out and "Pagina um Donas" in out and "de 2" in out, out[:300]

    def test_read_file_long_line_budget(self, ctx):
        run(agent(ctx).run_tool("create_file", {"path": "uploads/oneline.txt", "content": "x" * 150000}))
        out = run(agent(ctx).run_tool("read_file", {"path": "uploads/oneline.txt"}))
        assert len(out) < 19000 and "linha cortada" in out, len(out)
        # many medium lines stop at budget
        run(agent(ctx).run_tool("create_file", {"path": "uploads/many.txt", "content": "\n".join(["y" * 1500] * 50)}))
        out = run(agent(ctx).run_tool("read_file", {"path": "uploads/many.txt"}))
        assert len(out) < 20000 and "continue com start_line" in out

    def test_copy_dir_keep_name_and_overwrite(self, ctx):
        a = agent(ctx)
        out = run(a.run_tool("move_or_copy_file", {"source": "uploads/page.html", "dest": "frontend/public/", "mode": "copy"}))
        assert out.startswith("OK") and "frontend/public/page.html" in out, out
        out = run(a.run_tool("move_or_copy_file", {"source": "uploads/page.html", "dest": "frontend/public/"}))
        assert out.startswith("ERRO") and "já existe" in out, out
        out = run(a.run_tool("move_or_copy_file", {"source": "uploads/page.html", "dest": "frontend/public/", "overwrite": True}))
        assert out.startswith("OK"), out

    def test_move_binary(self, ctx):
        a = agent(ctx)
        upload(ctx, "logo.png", bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"))
        r = ctx["s"].get(f"{BASE_URL}/api/projects/{ctx['pid']}/asset", params={"path": "uploads/logo.png"})
        orig = r.content
        out = run(a.run_tool("move_or_copy_file", {"source": "uploads/logo.png", "dest": "frontend/public/img/logo2.png", "mode": "move"}))
        assert out.startswith("OK"), out
        files = {f["path"] for f in ctx["s"].get(f"{BASE_URL}/api/projects/{ctx['pid']}").json()["files"]}
        assert "uploads/logo.png" not in files and "frontend/public/img/logo2.png" in files
        r = ctx["s"].get(f"{BASE_URL}/api/projects/{ctx['pid']}/asset", params={"path": "frontend/public/img/logo2.png"})
        assert r.status_code == 200 and r.content == orig

    def test_clean_links_dry_run_and_real(self, ctx):
        a = agent(ctx)
        orig = make_big_html()
        out = run(a.run_tool("clean_external_links", {"source": "uploads/page.html", "dry_run": True}))
        assert out.startswith("DRY RUN") and "evil.com" in out and "img.cdn.com" in out, out
        files = {f["path"]: f for f in ctx["s"].get(f"{BASE_URL}/api/projects/{ctx['pid']}").json()["files"]}
        assert files["uploads/page.html"]["content"] == orig
        out = run(a.run_tool("clean_external_links", {"source": "uploads/page.html", "dest": "frontend/public/clean.html"}))
        assert out.startswith("OK"), out
        files = {f["path"]: f for f in ctx["s"].get(f"{BASE_URL}/api/projects/{ctx['pid']}").json()["files"]}
        c = files["frontend/public/clean.html"]["content"]
        assert files["uploads/page.html"]["content"] == orig  # source untouched
        assert "evil.com" not in c and 'href="#"' in c
        assert "cdn.tracker.com" not in c and '<script src="app.js"></script>' in c
        assert "img.cdn.com" not in c and 'src="img/local.png"' in c and 'srcset=""' in c
        assert 'src="about:blank"' in c and "youtube" not in c
        assert "preconnect" not in c
        assert "fonts.googleapis.com" in c  # stylesheet kept by default
        assert 'href="/local/page"' in c and 'href="local.css"' in c
        # byte-identical aside from expected substitutions
        exp = orig.replace('<link rel="preconnect" href="https://fonts.gstatic.com">', "")
        exp = exp.replace('<script src="https://cdn.tracker.com/t.js"></script>', "")
        exp = exp.replace('href="https://evil.com/page?x=1"', 'href="#"').replace('src="https://img.cdn.com/a.png"', 'src=""')
        exp = exp.replace('srcset="https://img.cdn.com/a1.png 1x, https://img.cdn.com/a2.png 2x"', 'srcset=""')
        exp = exp.replace('src="https://www.youtube.com/embed/x"', 'src="about:blank"')
        assert c == exp

    def test_extract_zip(self, ctx):
        out = run(agent(ctx).run_tool("extract_zip", {"source": "uploads/site.zip", "dest_dir": "uploads/site"}))
        assert out.startswith("OK") and "3 arquivos" in out, out
        files = {f["path"] for f in ctx["s"].get(f"{BASE_URL}/api/projects/{ctx['pid']}").json()["files"]}
        assert any(p.startswith("uploads/site/") and p.endswith("index.html") for p in files), files

    def test_search(self, ctx):
        a = agent(ctx)
        run(a.run_tool("create_file", {"path": "frontend/src/App.js", "content": "line1\nconst Foo = 1;\nfoo()\n"}))
        out = run(a.run_tool("search_in_files", {"query": "foo", "path_glob": "frontend/src/**/*.js"}))
        assert "frontend/src/App.js:2:7:" in out and "frontend/src/App.js:3:1:" in out, out
        out = run(a.run_tool("search_in_files", {"query": "Foo", "case_sensitive": True, "path_glob": "frontend/**"}))
        assert "App.js:2" in out and "App.js:3" not in out, out
        out = run(a.run_tool("search_in_files", {"query": r"const\s+\w+", "regex": True}))
        assert "App.js:2:1:" in out
        assert run(a.run_tool("search_in_files", {"query": "([", "regex": True})).startswith("ERRO")
        assert "App.js:2" in run(a.run_tool("search_files", {"query": "Foo"}))

    def test_empty_response_sets_error_and_length_warning(self, ctx):
        from core import db
        a = agent(ctx)

        async def empty(client, headers, model, messages):
            return "", [], None, None, None
        a.call_model = empty
        run(a.run("TEST_empty", "x", "k", "platform"))
        m = run(db.messages.find_one({"project_id": ctx["pid"], "role": "assistant"}, {"_id": 0}, sort=[("created_at", -1)]))
        assert m["error"] and "não retornou" in m["error"]
        b = agent(ctx)

        async def cut(client, headers, model, messages):
            return "parcial", [], None, None, "length"
        b.call_model = cut
        run(b.run("TEST_len", "x", "k", "platform"))
        m = run(db.messages.find_one({"project_id": ctx["pid"], "role": "assistant"}, {"_id": 0}, sort=[("created_at", -1)]))
        assert m["warnings"] and "limite de tokens" in m["warnings"][0] and not m["error"]

    def test_attachments_note_in_build_messages(self, ctx):
        from core import db, now, new_id
        run(db.messages.insert_one({"id": new_id(), "project_id": ctx["pid"], "role": "user", "content": "TEST_att",
                                    "attachments": [{"path": "uploads/page.html", "kind": "text", "size": 150000, "summary": "HTML grande"}],
                                    "created_at": now()}))
        msgs = run(agent(ctx).build_messages("TEST_att"))
        last = msgs[-1]["content"]
        assert "[ANEXOS" in last and "uploads/page.html" in last and "HTML grande" in last


class TestEnvAndVersions:
    def test_env_roundtrip_and_no_leak(self, ctx):
        s, pid = ctx["s"], ctx["pid"]
        r = s.put(f"{BASE_URL}/api/projects/{pid}/env", json={"vars": [{"key": "REACT_APP_TITLE", "value": "segredo123"}]})
        assert r.status_code == 200
        assert s.get(f"{BASE_URL}/api/projects/{pid}/env").json()["vars"] == [{"key": "REACT_APP_TITLE", "value": "segredo123"}]
        p = s.get(f"{BASE_URL}/api/projects/{pid}").json()["project"]
        assert p["env_keys"] == ["REACT_APP_TITLE"] and "env_enc" not in p
        assert s.put(f"{BASE_URL}/api/projects/{pid}/env", json={"vars": [{"key": "1BAD-K", "value": "x"}]}).status_code == 400
        lst = s.get(f"{BASE_URL}/api/projects").json()
        assert all("env_enc" not in x for x in lst)
        msgs = run(agent(ctx).build_messages("oi"))
        assert "REACT_APP_TITLE" in msgs[0]["content"] and "segredo123" not in msgs[0]["content"]

    def test_patch_does_not_leak_env_enc(self, ctx):
        r = ctx["s"].patch(f"{BASE_URL}/api/projects/{ctx['pid']}", json={"name": "TEST_iter4_tools"})
        assert r.status_code == 200
        assert "env_enc" not in r.json(), "PATCH /projects/{pid} returns env_enc"

    def test_restore_before_and_after(self, ctx):
        s, pid = ctx["s"], ctx["pid"]
        for c in ("v1", "v2", "v3"):
            assert s.put(f"{BASE_URL}/api/projects/{pid}/files", json={"path": "TEST_r.txt", "content": c}).status_code == 200
        vs = s.get(f"{BASE_URL}/api/projects/{pid}/versions").json()
        mine = [v for v in vs if "TEST_r.txt" in v["paths"]]
        v2 = mine[1]  # sorted desc: v3, v2, v1
        r = s.post(f"{BASE_URL}/api/projects/{pid}/versions/{v2['id']}/restore", params={"mode": "before"})
        assert r.status_code == 200 and r.json()["changed"] >= 1
        content = lambda: {f["path"]: f for f in s.get(f"{BASE_URL}/api/projects/{pid}").json()["files"]}["TEST_r.txt"]["content"]
        assert content() == "v1"
        r = s.post(f"{BASE_URL}/api/projects/{pid}/versions/{v2['id']}/restore", params={"mode": "after"})
        assert r.status_code == 200
        assert content() == "v2"
        # undo the latest (v1 created the file) -> file deleted
        v1 = mine[2]
        s.post(f"{BASE_URL}/api/projects/{pid}/versions/{v1['id']}/restore", params={"mode": "before"})
        files = {f["path"] for f in s.get(f"{BASE_URL}/api/projects/{pid}").json()["files"]}
        assert "TEST_r.txt" not in files
        assert s.post(f"{BASE_URL}/api/projects/{pid}/versions/{v1['id']}/restore", params={"mode": "bad"}).status_code == 422
