"""Runtime credential login and persisted bearer identity endpoints."""

from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from makepdf.web.auth import Identity, create_api_key, require_identity

router = APIRouter(prefix="/api", tags=["runtime-auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


@router.get("/auth/demo-credentials")
async def demo_credentials():
    if os.getenv("MAKEPDF_ENV", "production") == "production":
        raise HTTPException(status_code=404, detail="Demo credentials are unavailable in production")
    email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD", "")
    if not email or not password:
        raise HTTPException(status_code=503, detail="Local demo credentials are not provisioned")
    return {"email": email, "password": password}


@router.post("/auth/login")
async def login(payload: LoginRequest):
    expected_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    expected_password = os.getenv("ADMIN_PASSWORD", "")
    if not expected_email or not expected_password or not (
        hmac.compare_digest(payload.email.strip().lower(), expected_email)
        and hmac.compare_digest(payload.password, expected_password)
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    _key_id, token = create_api_key(
        os.getenv("MAKEPDF_TENANT_ID", "runtime-tenant"),
        expected_email,
        os.getenv("MAKEPDF_ROLE", "administrator"),
        "runtime-login-session",
        expires_in=24 * 60 * 60,
    )
    return {
        "token": token,
        "user": {
            "email": expected_email,
            "name": os.getenv("PROVISION_ADMIN_NAME", "Runtime Administrator"),
            "role": os.getenv("MAKEPDF_ROLE", "administrator"),
        },
    }


@router.get("/auth/me")
async def me(identity: Identity = Depends(require_identity)):
    return {
        "user": {
            "id": identity.key_id,
            "email": identity.user_id,
            "tenantId": identity.tenant_id,
            "role": identity.role,
        }
    }
