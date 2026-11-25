# Self-host (AUTH_MODE=selfhost) auth module tests, run in an isolated subprocess (selfhost_harness.py) on DB selfhost_test.
import os
import json
import secrets
import subprocess
import pytest

ADMIN = "dono@vps.com"
PW = "Senha-VPS-123"


@pytest.fixture(scope="module")
def r():
    env = {**os.environ, "AUTH_MODE": "selfhost", "ADMIN_EMAIL": ADMIN, "ADMIN_PASSWORD": PW,
           "JWT_SECRET": secrets.token_hex(32), "DB_NAME": "selfhost_test", "MONGO_URL": "mongodb://localhost:27017"}
    p = subprocess.run(["python", "/app/backend/tests/selfhost_harness.py"], env=env, capture_output=True, text=True, timeout=120)
    line = next((x for x in p.stdout.splitlines() if x.startswith("RESULT")), None)
    assert line, f"harness failed: {p.stderr[-2000:]}"
    return json.loads(line[6:])


class TestSelfHostAuth:
    def test_mode(self, r):
        assert r["auth_mode"] == "selfhost" and r["core_auth_mode"] == "selfhost"
        assert r["core_require_user_is_selfhost"] is True
        assert r["mode_endpoint"] == {"mode": "selfhost", "email_login": True}

    def test_bad_login(self, r):
        assert r["wrong_email"] == 401
        assert r["wrong_password"] == 401

    def test_good_login_case_insensitive(self, r):
        assert r["login_status"] == 200
        assert r["login_email"] == ADMIN
        assert r["token_is_str"] is True

    def test_require_user(self, r):
        assert r["whoami_status"] == 200
        assert r["whoami"]["user_id"] == "selfhost-admin"
        assert r["whoami"]["role"] == "admin"
        assert r["whoami"]["email"] == ADMIN

    def test_invalid_tokens(self, r):
        for k in ("no_token", "garbage_token", "wrong_secret_token", "expired_token", "alg_none_token"):
            assert r[k] == 401, k

    def test_current_member(self, r):
        assert r["member_status"] == 200 and r["member_second_status"] == 200
        assert r["member"]["role"] == "admin"
        assert r["member"]["email"] == ADMIN
        assert r["member"]["user_id"] == "selfhost-admin"
        assert r["users_in_db"] == 1

    def test_missing_config(self, r):
        assert r["missing_password"] == 503
        assert r["missing_email"] == 503
        assert r["missing_jwt_secret"] == 503

    def test_not_selfhost(self, r):
        assert r["login_when_clerk"] == 404
        assert r["mode_when_clerk"] == {"mode": "clerk", "email_login": False}
