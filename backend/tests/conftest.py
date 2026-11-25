import os
import subprocess
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
MEMBER_EMAIL = "forja.member+clerk_test@example.com"
ADMIN_EMAIL = "donas.admin+clerk_test@example.com"


def _token(email):
    out = subprocess.run(["python", "/app/backend/tests/clerk_token.py", email], capture_output=True, text=True, timeout=60)
    tok = out.stdout.strip()
    if not tok:
        pytest.skip(f"Could not get Clerk token: {out.stderr[-300:]}")
    return tok


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def member_token():
    return _token(MEMBER_EMAIL)


@pytest.fixture(scope="session")
def admin_token():
    return _token(ADMIN_EMAIL)


def _session(tok):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="session")
def member(member_token):
    return _session(member_token)


@pytest.fixture(scope="session")
def admin(admin_token):
    return _session(admin_token)


@pytest.fixture(scope="session")
def created_projects(member):
    ids = []
    yield ids
    for pid in ids:
        member.delete(f"{BASE_URL}/api/projects/{pid}")
