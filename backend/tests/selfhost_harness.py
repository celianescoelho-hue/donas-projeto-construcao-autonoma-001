# Isolated self-host auth harness: run in a fresh process with AUTH_MODE=selfhost env (see test_iter10_selfhost_auth.py).
# Prints a JSON dict of check results. Uses a separate DB (DB_NAME from env) and cleans up the user it creates.
import os
import sys
import json
import time

sys.path.insert(0, "/app/backend")
from dotenv import dotenv_values

# reuse encryption key from backend/.env, but keep the selfhost env passed in by the caller
os.environ.setdefault("FORJA_ENCRYPTION_KEY", dotenv_values("/app/backend/.env")["FORJA_ENCRYPTION_KEY"])
assert os.environ["DB_NAME"] != "test_database", "refusing to run selfhost harness on main DB"

import jwt
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

import self_auth
import core

out = {}
out["auth_mode"] = self_auth.auth_mode()
out["core_auth_mode"] = core.AUTH_MODE
out["core_require_user_is_selfhost"] = core.require_user is self_auth.require_user

app = FastAPI()
app.include_router(self_auth.self_router)


@app.get("/api/whoami")
def whoami(user: dict = Depends(self_auth.require_user)):
    return {k: v for k, v in user.items() if k != "claims"}


@app.get("/api/member")
async def member(m: dict = Depends(core.current_member)):
    return m


email, pw = os.environ["ADMIN_EMAIL"], os.environ["ADMIN_PASSWORD"]
with TestClient(app) as c:
    out["mode_endpoint"] = c.get("/api/auth/mode").json()
    out["wrong_email"] = c.post("/api/auth/login", json={"email": "x" + email, "password": pw}).status_code
    out["wrong_password"] = c.post("/api/auth/login", json={"email": email, "password": pw + "x"}).status_code
    r = c.post("/api/auth/login", json={"email": "  " + email.upper() + " ", "password": pw})
    out["login_status"] = r.status_code
    body = r.json()
    out["login_email"] = body.get("email")
    token = body.get("token", "")
    out["token_is_str"] = isinstance(token, str) and token.count(".") == 2
    w = c.get("/api/whoami", headers={"Authorization": f"Bearer {token}"})
    out["whoami_status"], out["whoami"] = w.status_code, w.json()
    out["no_token"] = c.get("/api/whoami").status_code
    out["garbage_token"] = c.get("/api/whoami", headers={"Authorization": "Bearer abc.def.ghi"}).status_code
    out["wrong_secret_token"] = c.get("/api/whoami", headers={"Authorization": "Bearer " + jwt.encode(
        {"sub": "selfhost-admin", "role": "admin", "exp": int(time.time()) + 60}, "z" * 64, algorithm="HS256")}).status_code
    out["expired_token"] = c.get("/api/whoami", headers={"Authorization": "Bearer " + jwt.encode(
        {"sub": "selfhost-admin", "role": "admin", "exp": int(time.time()) - 10}, os.environ["JWT_SECRET"], algorithm="HS256")}).status_code
    out["alg_none_token"] = c.get("/api/whoami", headers={"Authorization": "Bearer " + jwt.encode(
        {"sub": "selfhost-admin", "role": "admin"}, None, algorithm="none")}).status_code
    m = c.get("/api/member", headers={"Authorization": f"Bearer {token}"})
    out["member_status"], out["member"] = m.status_code, m.json()
    m2 = c.get("/api/member", headers={"Authorization": f"Bearer {token}"})
    out["member_second_status"] = m2.status_code

    # missing ADMIN_PASSWORD -> 503
    saved = os.environ.pop("ADMIN_PASSWORD")
    out["missing_password"] = c.post("/api/auth/login", json={"email": email, "password": "whatever"}).status_code
    os.environ["ADMIN_PASSWORD"] = saved
    saved = os.environ.pop("ADMIN_EMAIL")
    out["missing_email"] = c.post("/api/auth/login", json={"email": email, "password": pw}).status_code
    os.environ["ADMIN_EMAIL"] = saved
    # missing JWT_SECRET -> 503
    saved = os.environ.pop("JWT_SECRET")
    out["missing_jwt_secret"] = c.post("/api/auth/login", json={"email": email, "password": pw}).status_code
    os.environ["JWT_SECRET"] = saved
    # AUTH_MODE != selfhost -> 404
    os.environ["AUTH_MODE"] = "clerk"
    out["login_when_clerk"] = c.post("/api/auth/login", json={"email": email, "password": pw}).status_code
    out["mode_when_clerk"] = c.get("/api/auth/mode").json()
    os.environ["AUTH_MODE"] = "selfhost"

# cleanup only the user we created
import pymongo
pc = pymongo.MongoClient(os.environ["MONGO_URL"])
out["users_in_db"] = pc[os.environ["DB_NAME"]].users.count_documents({"user_id": "selfhost-admin"})
pc[os.environ["DB_NAME"]].users.delete_one({"user_id": "selfhost-admin"})
print("RESULT" + json.dumps(out, default=str))
