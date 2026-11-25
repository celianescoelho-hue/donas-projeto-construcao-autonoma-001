# Iteration 5: public Link Preview (PATCH public_preview flag, public preview + asset endpoints, hidden files, env filtering)
import pytest
import requests
from conftest import BASE_URL

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")
PUB = f"{BASE_URL}/api/public/projects"
anon = requests.Session()


@pytest.fixture(scope="module")
def ctx(member, created_projects):
    r = member.post(f"{BASE_URL}/api/projects", json={"name": "TEST_public_preview"})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    created_projects.append(pid)
    for path, content in [("frontend/src/App.jsx", "export default function App(){return <h1>Oi</h1>}"),
                          ("frontend/index.html", "<div id=root></div>"),
                          ("backend/server.py", "SECRET=1"), ("tools/x.py", "print(1)"),
                          ("frontend/.env", "A=1"), (".env.local", "B=2"), ("requirements.txt", "fastapi"),
                          ("backend/notes.md", "hidden")]:
        assert member.put(f"{BASE_URL}/api/projects/{pid}/files", json={"path": path, "content": content}).status_code == 200
    for name, data, d in [("logo.png", PNG, "frontend/public"), ("doc.pdf", b"%PDF-1.4\n%%EOF", "uploads"),
                          ("bk.png", PNG, "backend")]:
        member.post(f"{BASE_URL}/api/projects/{pid}/upload", files=[("files", (name, data))], data={"directory": d})
    r = member.put(f"{BASE_URL}/api/projects/{pid}/env", json={"vars": [
        {"key": "REACT_APP_API", "value": "https://x"}, {"key": "VITE_K", "value": "v"}, {"key": "SECRET_KEY", "value": "s3cr3t"}]})
    assert r.status_code == 200, r.text
    return {"s": member, "pid": pid}


class TestPublicPreview:
    def test_disabled_by_default_404(self, ctx):
        r = anon.get(f"{PUB}/{ctx['pid']}/preview")
        assert r.status_code == 404
        assert r.json()["detail"] == "Esta prévia não é pública ou não existe."
        assert anon.get(f"{PUB}/{ctx['pid']}/asset", params={"path": "frontend/public/logo.png"}).status_code == 404

    def test_unknown_id_404(self):
        r = anon.get(f"{PUB}/does-not-exist-123/preview")
        assert r.status_code == 404
        assert r.json()["detail"] == "Esta prévia não é pública ou não existe."

    def test_patch_enable_no_env_enc(self, ctx):
        r = ctx["s"].patch(f"{BASE_URL}/api/projects/{ctx['pid']}", json={"public_preview": True})
        assert r.status_code == 200
        j = r.json()
        assert j["public_preview"] is True
        assert "env_enc" not in j and "_id" not in j
        g = ctx["s"].get(f"{BASE_URL}/api/projects/{ctx['pid']}").json()["project"]
        assert g["public_preview"] is True and "env_enc" not in g

    def test_enabled_preview_content(self, ctx):
        r = anon.get(f"{PUB}/{ctx['pid']}/preview")
        assert r.status_code == 200, r.text
        j = r.json()
        assert set(j) == {"name", "updated_at", "env", "files"}
        assert j["name"] == "TEST_public_preview"
        assert j["env"] == {"REACT_APP_API": "https://x", "VITE_K": "v"}
        paths = {f["path"] for f in j["files"]}
        assert "frontend/src/App.jsx" in paths and "frontend/index.html" in paths
        assert "frontend/public/logo.png" in paths
        for bad in ["backend/server.py", "tools/x.py", "frontend/.env", ".env.local", "requirements.txt",
                    "backend/notes.md", "uploads/doc.pdf", "backend/bk.png"]:
            assert bad not in paths, bad
        assert "s3cr3t" not in r.text

    def test_asset_image_ok(self, ctx):
        r = anon.get(f"{PUB}/{ctx['pid']}/asset", params={"path": "frontend/public/logo.png"})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/png")
        assert r.content == PNG

    @pytest.mark.parametrize("path", ["backend/bk.png", "uploads/doc.pdf", "frontend/src/App.jsx", "backend/server.py", "nope.png", "../backend/bk.png"])
    def test_asset_hidden_404(self, ctx, path):
        assert anon.get(f"{PUB}/{ctx['pid']}/asset", params={"path": path}).status_code in (400, 404)

    def test_stamp_changes_on_file_edit(self, ctx):
        s1 = anon.get(f"{PUB}/{ctx['pid']}/preview").json()["updated_at"]
        ctx["s"].put(f"{BASE_URL}/api/projects/{ctx['pid']}/files", json={"path": "frontend/src/App.jsx", "content": "export default function App(){return <h1>Oi2</h1>}"})
        j = anon.get(f"{PUB}/{ctx['pid']}/preview").json()
        assert j["updated_at"] != s1
        assert any("Oi2" in (f["content"] or "") for f in j["files"])

    def test_patch_disable(self, ctx):
        r = ctx["s"].patch(f"{BASE_URL}/api/projects/{ctx['pid']}", json={"public_preview": False})
        assert r.status_code == 200 and r.json()["public_preview"] is False and "env_enc" not in r.json()
        assert anon.get(f"{PUB}/{ctx['pid']}/preview").status_code == 404
        assert anon.get(f"{PUB}/{ctx['pid']}/asset", params={"path": "frontend/public/logo.png"}).status_code == 404

    def test_patch_requires_auth_and_ownership(self, ctx, admin):
        assert anon.patch(f"{BASE_URL}/api/projects/{ctx['pid']}", json={"public_preview": True}).status_code in (401, 403)
        r = admin.patch(f"{BASE_URL}/api/projects/{ctx['pid']}", json={"public_preview": True})
        assert r.status_code in (403, 404)
        assert anon.get(f"{PUB}/{ctx['pid']}/preview").status_code == 404

    def test_patch_bad_type(self, ctx):
        assert ctx["s"].patch(f"{BASE_URL}/api/projects/{ctx['pid']}", json={"public_preview": "maybe"}).status_code == 422
