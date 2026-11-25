# Preview (AUTH_MODE=clerk) regression after auth refactor: auth mode, login 404, /me, models, project CRUD, 401s.
import requests

from conftest import BASE_URL


class TestClerkPreviewRegression:
    def test_auth_mode(self):
        r = requests.get(f"{BASE_URL}/api/auth/mode")
        assert r.status_code == 200
        assert r.json() == {"mode": "clerk", "email_login": False}

    def test_email_login_disabled(self):
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "dono@vps.com", "password": "Senha-VPS-123"})
        assert r.status_code == 404

    def test_protected_without_token(self):
        for p in ("/api/me", "/api/projects", "/api/models"):
            assert requests.get(f"{BASE_URL}{p}").status_code == 401, p

    def test_selfhost_style_token_rejected(self):
        r = requests.get(f"{BASE_URL}/api/me", headers={"Authorization": "Bearer abc.def.ghi"})
        assert r.status_code == 401

    def test_me_member(self, member):
        r = member.get(f"{BASE_URL}/api/me")
        assert r.status_code == 200
        d = r.json()
        assert d["email"] == "forja.member+clerk_test@example.com"
        assert d["role"] in ("member", "admin")

    def test_me_admin(self, admin):
        r = admin.get(f"{BASE_URL}/api/me")
        assert r.status_code == 200
        assert r.json()["email"] == "donas.admin+clerk_test@example.com"

    def test_models(self, member):
        r = member.get(f"{BASE_URL}/api/models")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d["models"], list) and len(d["models"]) > 0 and d["default_model"]

    def test_project_crud(self, member):
        r = member.post(f"{BASE_URL}/api/projects", json={"name": "TEST_iter10_crud"})
        assert r.status_code == 200
        pid = r.json()["id"]
        try:
            assert any(p["id"] == pid for p in member.get(f"{BASE_URL}/api/projects").json())
            r = member.patch(f"{BASE_URL}/api/projects/{pid}", json={"name": "TEST_iter10_renamed"})
            assert r.status_code == 200 and r.json()["name"] == "TEST_iter10_renamed"
            g = member.get(f"{BASE_URL}/api/projects/{pid}")
            assert g.status_code == 200 and g.json()["project"]["name"] == "TEST_iter10_renamed"
        finally:
            d = member.delete(f"{BASE_URL}/api/projects/{pid}")
        assert d.status_code == 200
        assert member.get(f"{BASE_URL}/api/projects/{pid}").status_code == 404
