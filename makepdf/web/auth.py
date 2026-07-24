"""Tenant/user API-key identity, rotation, roles, and signed artifact URLs."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.security.api_key import APIKeyHeader

from makepdf.web.job_registry import _connect, append_audit, initialize as initialize_jobs

logger = logging.getLogger(__name__)
ROLES = {"administrator", "operator", "auditor"}
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer_header = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Identity:
    tenant_id: str
    user_id: str
    role: str
    key_id: str

    @property
    def is_admin(self) -> bool:
        return self.role == "administrator"


def initialize_identity() -> None:
    initialize_jobs()
    with _connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
              key_id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              role TEXT NOT NULL CHECK(role IN ('administrator','operator','auditor')),
              secret_hash TEXT NOT NULL,
              label TEXT NOT NULL,
              rotated_from TEXT REFERENCES api_keys(key_id),
              created_at REAL NOT NULL,
              expires_at REAL NOT NULL,
              last_used_at REAL,
              revoked_at REAL
            );
            CREATE INDEX IF NOT EXISTS api_keys_tenant_user
              ON api_keys(tenant_id,user_id) WHERE revoked_at IS NULL;

            CREATE TABLE IF NOT EXISTS documents (
              id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL,
              owner_user_id TEXT NOT NULL,
              source_path TEXT NOT NULL,
              source_sha256 TEXT NOT NULL,
              size_bytes INTEGER NOT NULL,
              page_count INTEGER,
              status TEXT NOT NULL CHECK(status IN ('quarantined','active','deletion-pending','deleted')),
              retention_until REAL NOT NULL,
              legal_hold INTEGER NOT NULL DEFAULT 0,
              created_at REAL NOT NULL,
              deleted_at REAL
            );
            CREATE INDEX IF NOT EXISTS documents_tenant_owner
              ON documents(tenant_id,owner_user_id,status);

            CREATE TABLE IF NOT EXISTS usage_daily (
              tenant_id TEXT NOT NULL,
              day TEXT NOT NULL,
              request_count INTEGER NOT NULL DEFAULT 0,
              uploaded_bytes INTEGER NOT NULL DEFAULT 0,
              job_count INTEGER NOT NULL DEFAULT 0,
              PRIMARY KEY(tenant_id,day)
            );

            CREATE TABLE IF NOT EXISTS billing_exports (
              id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL,
              day TEXT NOT NULL,
              usage_json TEXT NOT NULL,
              usage_sha256 TEXT NOT NULL,
              created_by TEXT NOT NULL,
              created_at REAL NOT NULL,
              UNIQUE(tenant_id,day)
            );
            """
        )


def _secret_hash(secret: str) -> str:
    pepper = os.getenv("MAKEPDF_API_KEY_PEPPER", "")
    return hashlib.sha256(f"{pepper}:{secret}".encode()).hexdigest()


def create_api_key(
    tenant_id: str,
    user_id: str,
    role: str,
    label: str,
    *,
    expires_in: int = 90 * 86400,
    rotated_from: str | None = None,
) -> tuple[str, str]:
    if role not in ROLES:
        raise ValueError(f"Unsupported role: {role}")
    if not tenant_id.strip() or not user_id.strip() or not label.strip():
        raise ValueError("tenant_id, user_id, and label are required")
    initialize_identity()
    key_id = secrets.token_hex(10)
    secret = secrets.token_urlsafe(32)
    now = time.time()
    with _connect() as db:
        db.execute(
            "INSERT INTO api_keys(key_id,tenant_id,user_id,role,secret_hash,label,rotated_from,created_at,expires_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (key_id, tenant_id, user_id, role, _secret_hash(secret), label, rotated_from, now, now + expires_in),
        )
    append_audit(tenant_id, user_id, "api_key.created", "api_key", key_id, {"role": role, "label": label})
    return key_id, f"mpk_{key_id}.{secret}"


def rotate_api_key(identity: Identity, key_id: str, expires_in: int = 90 * 86400) -> tuple[str, str]:
    if not identity.is_admin:
        raise PermissionError("Administrator role is required")
    initialize_identity()
    with _connect() as db:
        old = db.execute(
            "SELECT * FROM api_keys WHERE key_id=? AND tenant_id=? AND revoked_at IS NULL",
            (key_id, identity.tenant_id),
        ).fetchone()
        if not old:
            raise KeyError(key_id)
    new_id, raw = create_api_key(
        identity.tenant_id,
        old["user_id"],
        old["role"],
        f"rotation-of-{old['label']}",
        expires_in=expires_in,
        rotated_from=key_id,
    )
    with _connect() as db:
        db.execute("UPDATE api_keys SET revoked_at=? WHERE key_id=?", (time.time(), key_id))
    append_audit(identity.tenant_id, identity.user_id, "api_key.rotated", "api_key", key_id, {"replacement": new_id})
    return new_id, raw


def _stored_identity(api_key: str) -> Identity | None:
    if not api_key.startswith("mpk_") or "." not in api_key:
        return None
    key_id, secret = api_key[4:].split(".", 1)
    initialize_identity()
    with _connect() as db:
        row = db.execute("SELECT * FROM api_keys WHERE key_id=?", (key_id,)).fetchone()
        if not row or row["revoked_at"] or row["expires_at"] <= time.time():
            return None
        if not hmac.compare_digest(row["secret_hash"], _secret_hash(secret)):
            return None
        db.execute("UPDATE api_keys SET last_used_at=? WHERE key_id=?", (time.time(), key_id))
        return Identity(row["tenant_id"], row["user_id"], row["role"], row["key_id"])


def authenticate_api_key(api_key: str | None) -> Identity | None:
    if api_key:
        stored = _stored_identity(api_key)
        if stored:
            return stored
    legacy = os.getenv("API_KEY")
    if legacy and api_key and secrets.compare_digest(api_key, legacy):
        return Identity(
            os.getenv("MAKEPDF_TENANT_ID", "legacy"),
            os.getenv("MAKEPDF_USER_ID", "legacy-admin"),
            os.getenv("MAKEPDF_ROLE", "administrator"),
            "environment",
        )
    return None


async def require_identity(
    api_key: str | None = Security(_api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Security(_bearer_header),
) -> Identity:
    bearer_token = bearer.credentials if isinstance(bearer, HTTPAuthorizationCredentials) else None
    identity = authenticate_api_key(api_key or bearer_token)
    if identity:
        return identity
    if not os.getenv("API_KEY") and os.getenv("MAKEPDF_ALLOW_OPEN_MODE", "").lower() in {"1", "true", "yes"}:
        return Identity("development", "anonymous", "administrator", "open-mode")
    if not os.getenv("API_KEY"):
        raise HTTPException(status_code=503, detail="No production identity provider is configured.")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid, expired, revoked, or missing X-API-Key.",
        headers={"WWW-Authenticate": "ApiKey"},
    )


async def require_api_key(
    api_key: str | None = Security(_api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Security(_bearer_header),
) -> Identity:
    """Backward-compatible dependency name; now returns a tenant user identity."""
    return await require_identity(api_key, bearer)


def require_role(identity: Identity, *roles: str) -> None:
    if identity.role not in roles:
        raise HTTPException(status_code=403, detail=f"One of these roles is required: {', '.join(roles)}")


def _download_keys() -> tuple[str, dict[str, str]]:
    raw = os.getenv("MAKEPDF_DOWNLOAD_SIGNING_KEYS", "")
    try:
        keys = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError("MAKEPDF_DOWNLOAD_SIGNING_KEYS must be a JSON object") from exc
    if not isinstance(keys, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in keys.items()):
        raise RuntimeError("Download signing keys must be a string-to-string JSON object")
    active = os.getenv("MAKEPDF_ACTIVE_SIGNING_KEY", "")
    if not active or active not in keys or len(keys[active]) < 32:
        # Development-only deterministic key keeps tests ergonomic. Production
        # startup validation rejects it.
        if os.getenv("MAKEPDF_ENV", "development").lower() == "production":
            raise RuntimeError("An active 32+ character download signing key is required")
        keys = {"development": "development-only-signing-key-change-me"}
        active = "development"
    return active, keys


def sign_download(job_id: str, identity: Identity, ttl_seconds: int = 300) -> str:
    active, keys = _download_keys()
    expires = int(time.time()) + min(max(ttl_seconds, 1), 900)
    material = f"{active}.{job_id}.{identity.tenant_id}.{identity.user_id}.{expires}"
    signature = hmac.new(keys[active].encode(), material.encode(), hashlib.sha256).hexdigest()
    return f"{active}.{expires}.{identity.user_id}.{signature}"


def verify_download(token: str, job_id: str, tenant_id: str) -> str | None:
    try:
        key_id, expires_raw, user_id, signature = token.split(".", 3)
        expires = int(expires_raw)
        _, keys = _download_keys()
        if expires < int(time.time()) or expires > int(time.time()) + 900 or key_id not in keys:
            return None
        material = f"{key_id}.{job_id}.{tenant_id}.{user_id}.{expires}"
        expected = hmac.new(keys[key_id].encode(), material.encode(), hashlib.sha256).hexdigest()
        return user_id if hmac.compare_digest(signature, expected) else None
    except (ValueError, KeyError):
        return None
