"""Self-hosted email/password auth for running Donas on your own VPS, fully
independent of Emergent/Clerk. Active only when AUTH_MODE=selfhost. A single
admin account comes from ADMIN_EMAIL + ADMIN_PASSWORD; sessions are own JWTs
signed with JWT_SECRET. In the Emergent preview AUTH_MODE is unset, so this
module stays inert and Clerk keeps handling login."""

import os
import hmac
import time

import jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

self_router = APIRouter(prefix="/api")
ALGO = "HS256"
TTL = 7 * 24 * 3600
ADMIN_USER_ID = "selfhost-admin"


def auth_mode() -> str:
    return os.environ.get("AUTH_MODE", "clerk").strip().lower()


def _admin_email() -> str:
    return (os.environ.get("ADMIN_EMAIL", "").split(",")[0]).strip()


def _jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="JWT_SECRET não configurado no backend/.env.")
    return secret


@self_router.get("/auth/mode")
def get_auth_mode():
    """Public: the frontend uses this to pick the login UI."""
    mode = auth_mode()
    return {"mode": mode, "email_login": mode == "selfhost"}


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=400)


@self_router.post("/auth/login")
def login(body: LoginIn, request: Request):
    if auth_mode() != "selfhost":
        raise HTTPException(status_code=404, detail="Login por e-mail/senha não está ativo neste ambiente.")
    try:
        from backend.core import rate_limit
    except ModuleNotFoundError:
        from core import rate_limit
    ip = (request.headers.get("x-real-ip") or request.headers.get("x-forwarded-for", "").split(",")[0]
          or (request.client.host if request.client else "")).strip()
    rate_limit(f"login:{ip}", 5, 60)
    email, password = _admin_email(), os.environ.get("ADMIN_PASSWORD", "")
    if not email or not password:
        raise HTTPException(status_code=503, detail="Defina ADMIN_EMAIL e ADMIN_PASSWORD no backend/.env.")
    ok = hmac.compare_digest(body.email.strip().lower(), email.lower()) & hmac.compare_digest(body.password, password)
    if not ok:
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
    now = int(time.time())
    token = jwt.encode({"sub": ADMIN_USER_ID, "email": email, "role": "admin", "iat": now, "exp": now + TTL},
                       _jwt_secret(), algorithm=ALGO)
    return {"token": token, "email": email}


def require_user(request: Request) -> dict:
    """FastAPI dependency mirroring clerk_auth.require_user, for self-host mode."""
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else ""
    if not token:
        raise HTTPException(status_code=401, detail="Not signed in")
    try:
        claims = jwt.decode(token, _jwt_secret(), algorithms=[ALGO])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada")
    return {"user_id": claims["sub"], "email": claims.get("email", ""),
            "role": claims.get("role", "member"), "claims": claims}
