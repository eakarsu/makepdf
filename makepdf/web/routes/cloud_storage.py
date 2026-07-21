"""Explicitly enabled, tenant-scoped cloud connectors with SSRF-safe imports."""

from __future__ import annotations

import ipaddress
import os
import socket
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.datastructures import UploadFile

from makepdf.config import MAX_UPLOAD_SIZE
from makepdf.web.auth import Identity, require_identity
from makepdf.web.governance import consume_quota, register_document
from makepdf.web.intake import save_upload
from makepdf.web.job_registry import _connect, append_audit, initialize

router = APIRouter(prefix="/api/cloud-storage", tags=["cloud-storage"])


class WebhookReg(BaseModel):
    provider: str
    folder_id: Optional[str] = None
    callback_url: str


def _enabled() -> None:
    if os.getenv("MAKEPDF_ALLOW_CLOUD", "").lower() not in {"1", "true", "yes"}:
        raise HTTPException(status_code=503, detail="Cloud processing is disabled by the data-processing boundary.")


def _initialize_cloud() -> None:
    initialize()
    with _connect() as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS cloud_webhooks (id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,"
            "user_id TEXT NOT NULL,provider TEXT NOT NULL,folder_id TEXT,callback_url TEXT NOT NULL,"
            "created_at REAL NOT NULL,UNIQUE(tenant_id,provider,folder_id,callback_url))"
        )


def _allowed_domains(variable: str) -> set[str]:
    return {item.strip().lower() for item in os.getenv(variable, "").split(",") if item.strip()}


def _validated_https_url(value: str, allowed: set[str]) -> str:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail="Only credential-free HTTPS URLs are permitted.")
    if host not in allowed:
        raise HTTPException(status_code=422, detail="URL hostname is not in the configured allowlist.")
    try:
        addresses = {entry[4][0] for entry in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise HTTPException(status_code=422, detail="URL hostname could not be resolved.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise HTTPException(status_code=422, detail="Private or special network targets are forbidden.")
    return value


@router.post("/webhooks/register", status_code=201)
async def register_webhook(payload: WebhookReg, identity: Identity = Depends(require_identity)):
    _enabled()
    if payload.provider not in {"gdrive", "dropbox", "box", "sharepoint"}:
        raise HTTPException(status_code=422, detail="Unsupported cloud provider.")
    callback = _validated_https_url(payload.callback_url, _allowed_domains("MAKEPDF_WEBHOOK_CALLBACK_DOMAINS"))
    _initialize_cloud()
    webhook_id = str(uuid.uuid4())
    with _connect() as db:
        db.execute(
            "INSERT INTO cloud_webhooks(id,tenant_id,user_id,provider,folder_id,callback_url,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (webhook_id, identity.tenant_id, identity.user_id, payload.provider, payload.folder_id, callback, time.time()),
        )
    append_audit(identity.tenant_id, identity.user_id, "cloud_webhook.created", "cloud_webhook", webhook_id)
    return {"id": webhook_id, "provider": payload.provider, "folder_id": payload.folder_id}


@router.get("/webhooks")
async def list_webhooks(identity: Identity = Depends(require_identity)):
    _enabled()
    _initialize_cloud()
    with _connect() as db:
        rows = db.execute(
            "SELECT id,provider,folder_id,callback_url,created_at FROM cloud_webhooks WHERE tenant_id=?",
            (identity.tenant_id,),
        ).fetchall()
    return {"count": len(rows), "webhooks": [dict(row) for row in rows]}


@router.get("/list")
async def list_files(provider: str, folder_id: Optional[str] = None, identity: Identity = Depends(require_identity)):
    _enabled()
    consume_quota(identity)
    if provider == "dropbox":
        token = os.getenv("DROPBOX_ACCESS_TOKEN")
        if not token:
            raise HTTPException(503, "DROPBOX_ACCESS_TOKEN not configured")
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.post(
                "https://api.dropboxapi.com/2/files/list_folder",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"path": folder_id or ""},
            )
    elif provider == "box":
        token = os.getenv("BOX_DEVELOPER_TOKEN")
        if not token:
            raise HTTPException(503, "BOX_DEVELOPER_TOKEN not configured")
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            response = await client.get(
                f"https://api.box.com/2.0/folders/{folder_id or '0'}/items",
                headers={"Authorization": f"Bearer {token}"},
            )
    else:
        raise HTTPException(422, f"Unsupported provider: {provider}")
    if response.status_code >= 400:
        raise HTTPException(502, f"Cloud provider returned {response.status_code}")
    return response.json()


@router.post("/import-url", status_code=201)
async def import_url(payload: dict, identity: Identity = Depends(require_identity)):
    _enabled()
    url = _validated_https_url(str(payload.get("url", "")), _allowed_domains("MAKEPDF_CLOUD_IMPORT_DOMAINS"))
    name = Path(str(payload.get("name", "imported.pdf"))).name
    if Path(name).suffix.lower() != ".pdf":
        raise HTTPException(status_code=422, detail="Cloud imports must be PDF files.")
    spool = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
    total = 0
    async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
        async with client.stream("GET", url, headers={"Accept": "application/pdf"}) as response:
            if response.status_code != 200:
                raise HTTPException(502, f"Cloud import returned {response.status_code}")
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail="Cloud import exceeds the upload limit.")
                spool.write(chunk)
    spool.seek(0)
    intake = await save_upload(UploadFile(spool, filename=name), ".pdf", tenant_id=identity.tenant_id, durable=True)
    consume_quota(identity, uploaded_bytes=intake.size)
    document_id = register_document(identity, intake)
    return {"document_id": document_id, "sha256": intake.sha256, "bytes": intake.size}
