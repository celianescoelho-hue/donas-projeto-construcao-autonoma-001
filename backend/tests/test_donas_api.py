# Donas backend regression tests: me/models, projects CRUD, files, upload/asset/zip, versions/restore,
# admin/roles/block, settings validation, rate limit, path validation. Run with: pytest -n 0 tests/test_donas_api.py
import io
import zipfile
import struct
import zlib
import pytest
import requests
from conftest import BASE_URL

API = f"{BASE_URL}/api"


def tiny_png():
    raw = b"\x00\xff\x00\x00"
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


# --- me / models / auth
class TestMeModels:
    def test_unauth(self):
        assert requests.get(f"{API}/me").status_code in (401, 403)

    def test_me_member(self, member):
        r = member.get(f"{API}/me")
        assert r.status_code == 200
        d = r.json()
        assert d["role"] == "member" and d["email"].startswith("forja.member")
        assert isinstance(d["has_openrouter_key"], bool)
        assert not any(k in d for k in ("openrouter_key_enc", "github_token_enc", "openrouter_key", "key"))

    def test_models(self, member):
        d = member.get(f"{API}/models").json()
        assert any(m["id"] == "qwen/qwen3-coder-next" for m in d["models"])
        assert d["default_model"]


# --- projects + files + versions
class TestProjects:
    def test_full_flow(self, member, created_projects):
        r = member.post(f"{API}/projects", json={"name": "TEST_proj"})
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        created_projects.append(pid)
        assert r.json()["name"] == "TEST_proj"
        # rename
        r = member.patch(f"{API}/projects/{pid}", json={"name": "TEST_renamed"})
        assert r.status_code == 200 and r.json()["name"] == "TEST_renamed"
        assert any(p["id"] == pid and p["name"] == "TEST_renamed" for p in member.get(f"{API}/projects").json())
        # invalid model
        assert member.patch(f"{API}/projects/{pid}", json={"model": "bad/model"}).status_code == 400
        # empty name
        assert member.post(f"{API}/projects", json={"name": ""}).status_code == 422
        # save file v1, v2
        assert member.put(f"{API}/projects/{pid}/files", json={"path": "a/x.txt", "content": "one"}).json()["ok"]
        assert member.put(f"{API}/projects/{pid}/files", json={"path": "a/x.txt", "content": "two"}).status_code == 200
        unchanged = member.put(f"{API}/projects/{pid}/files", json={"path": "a/x.txt", "content": "two"}).json()
        assert unchanged.get("unchanged") is True
        files = {f["path"]: f for f in member.get(f"{API}/projects/{pid}").json()["files"]}
        assert files["a/x.txt"]["content"] == "two"
        # upload text + png
        up = member.post(f"{API}/projects/{pid}/upload", data={"directory": "frontend/public"},
                         files=[("files", ("index.html", b"<html><title>Hi</title><header id='top'></header><h1>Ola</h1></html>", "text/html")),
                                ("files", ("logo.png", tiny_png(), "image/png")),
                                ("files", ("bad.exe", b"MZ", "application/octet-stream"))])
        assert up.status_code == 200, up.text
        ud = up.json()
        paths = {s["path"]: s for s in ud["saved"]}
        assert "frontend/public/index.html" in paths and "frontend/public/logo.png" in paths
        assert "Título: Hi" in paths["frontend/public/index.html"]["summary"]
        assert "1x1px" in paths["frontend/public/logo.png"]["summary"]
        assert any("bad.exe" in e for e in ud["errors"])
        # asset
        a = member.get(f"{API}/projects/{pid}/asset", params={"path": "frontend/public/logo.png"})
        assert a.status_code == 200 and a.content[:4] == b"\x89PNG" and a.headers["content-type"] == "image/png"
        assert member.get(f"{API}/projects/{pid}/asset", params={"path": "nope.png"}).status_code == 404
        # zip
        z = member.get(f"{API}/projects/{pid}/zip")
        assert z.status_code == 200
        names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
        assert set(names) >= {"a/x.txt", "frontend/public/index.html", "frontend/public/logo.png"}
        # binary edit rejected
        assert member.put(f"{API}/projects/{pid}/files", json={"path": "frontend/public/logo.png", "content": "x"}).status_code == 400
        # versions: 1 (x one), 2 (x two), 3 (upload)
        vs = member.get(f"{API}/projects/{pid}/versions").json()
        assert [v["number"] for v in vs] == [3, 2, 1]
        v1 = [v for v in vs if v["number"] == 1][0]
        r = member.post(f"{API}/projects/{pid}/versions/{v1['id']}/restore")
        assert r.status_code == 200, r.text
        files = {f["path"]: f for f in member.get(f"{API}/projects/{pid}").json()["files"]}
        assert files["a/x.txt"]["content"] == "one"
        assert "frontend/public/logo.png" not in files
        vs = member.get(f"{API}/projects/{pid}/versions").json()
        assert vs[0]["source"] == "restore" and vs[0]["number"] == 4
        assert member.post(f"{API}/projects/{pid}/versions/nope/restore").status_code == 404
        # delete file
        assert member.delete(f"{API}/projects/{pid}/files", params={"path": "a/x.txt"}).status_code == 200
        assert member.delete(f"{API}/projects/{pid}/files", params={"path": "a/x.txt"}).status_code == 404
        # other user cannot access
        # delete project
        assert member.delete(f"{API}/projects/{pid}").status_code == 200
        assert member.get(f"{API}/projects/{pid}").status_code == 404

    def test_isolation(self, member, admin, created_projects):
        pid = member.post(f"{API}/projects", json={"name": "TEST_iso"}).json()["id"]
        created_projects.append(pid)
        assert admin.get(f"{API}/projects/{pid}").status_code == 404
        assert admin.delete(f"{API}/projects/{pid}").status_code == 404

    def test_path_traversal_rejected_cleanly(self, member, created_projects):
        pid = member.post(f"{API}/projects", json={"name": "TEST_trav"}).json()["id"]
        created_projects.append(pid)
        r = member.put(f"{API}/projects/{pid}/files", json={"path": "../etc/x.txt", "content": "x"})
        assert r.status_code == 400, f"expected 400 got {r.status_code}"

    def test_path_traversal_asset(self, member, created_projects):
        pid = member.post(f"{API}/projects", json={"name": "TEST_trav2"}).json()["id"]
        created_projects.append(pid)
        r = member.get(f"{API}/projects/{pid}/asset", params={"path": "../x.png"})
        assert r.status_code in (400, 404), f"expected 400/404 got {r.status_code}"


# --- admin
class TestAdmin:
    @pytest.mark.parametrize("path", ["/admin/overview", "/users", "/admin/settings", "/admin/usage"])
    def test_member_forbidden(self, member, path):
        assert member.get(f"{API}{path}").status_code == 403

    @pytest.mark.parametrize("path", ["/admin/overview", "/users", "/admin/settings", "/admin/usage"])
    def test_admin_ok(self, admin, path):
        assert admin.get(f"{API}{path}").status_code == 200

    def test_member_cannot_patch(self, member):
        assert member.patch(f"{API}/users/x/role", json={"role": "admin"}).status_code == 403
        assert member.put(f"{API}/admin/settings", json={"daily_limit_usd": 100}).status_code == 403

    def test_settings_roundtrip(self, admin):
        s = admin.get(f"{API}/admin/settings").json()
        orig = s["daily_limit_usd"]
        r = admin.put(f"{API}/admin/settings", json={"daily_limit_usd": orig + 1})
        assert r.status_code == 200 and r.json()["daily_limit_usd"] == orig + 1
        assert admin.put(f"{API}/admin/settings", json={"enabled_models": []}).status_code == 400
        admin.put(f"{API}/admin/settings", json={"daily_limit_usd": orig})
        assert admin.get(f"{API}/admin/settings").json()["daily_limit_usd"] == orig

    def test_roles_and_last_admin(self, admin, member):
        users = admin.get(f"{API}/users").json()["users"]
        me_m = member.get(f"{API}/me").json()
        me_a = admin.get(f"{API}/me").json()
        assert admin.patch(f"{API}/users/{me_m['user_id']}/role", json={"role": "god"}).status_code == 403
        assert admin.patch(f"{API}/users/nope/role", json={"role": "member"}).status_code == 404
        # promote then demote member
        try:
            r = admin.patch(f"{API}/users/{me_m['user_id']}/role", json={"role": "admin"})
            assert r.status_code == 200
            assert member.get(f"{API}/me").json()["role"] == "admin"
        finally:
            r = admin.patch(f"{API}/users/{me_m['user_id']}/role", json={"role": "member"})
        assert r.status_code == 200
        assert member.get(f"{API}/me").json()["role"] == "member"
        admins = [u for u in admin.get(f"{API}/users").json()["users"] if u["role"] == "admin"]
        if len(admins) == 1:
            assert admin.patch(f"{API}/users/{me_a['user_id']}/role", json={"role": "member"}).status_code == 409
        else:
            pytest.skip(f"{len(admins)} admins present; cannot safely test last-admin 409")

    def test_block_flow(self, admin, member):
        uid = member.get(f"{API}/me").json()["user_id"]
        me_a = admin.get(f"{API}/me").json()
        assert admin.patch(f"{API}/admin/users/{me_a['user_id']}/block", json={"blocked": True}).status_code == 400
        try:
            assert admin.patch(f"{API}/admin/users/{uid}/block", json={"blocked": True}).status_code == 200
            assert member.get(f"{API}/me").json()["blocked"] is True
            assert member.post(f"{API}/projects", json={"name": "TEST_blocked"}).status_code == 403
            assert member.post(f"{API}/projects/b3d78ab7-df29-4b70-8af0-f50a538bc67b/chat", json={"prompt": "oi"}).status_code == 403
        finally:
            r = admin.patch(f"{API}/admin/users/{uid}/block", json={"blocked": False})
            assert r.status_code == 200
        assert member.get(f"{API}/me").json()["blocked"] is False


# --- settings validation + rate limit
class TestSettings:
    def test_github_invalid(self, admin):
        r = admin.put(f"{API}/settings/github", json={"token": "ghp_invalidtoken123456"})
        assert r.status_code == 400
        assert admin.get(f"{API}/me").json()["github_login"] is None

    def test_github_required(self, member):
        assert member.get(f"{API}/github/repos").status_code == 400

    def test_openrouter_invalid_then_429(self, admin):
        codes = [admin.put(f"{API}/settings/openrouter-key", json={"key": "sk-or-invalid-0000000"}).status_code for _ in range(7)]
        print("codes", codes)
        assert codes[0] == 400
        assert 429 in codes
        assert admin.get(f"{API}/me").json()["has_openrouter_key"] is False

    def test_short_key_422(self, member):
        assert member.put(f"{API}/settings/openrouter-key", json={"key": "abc"}).status_code == 422
