"""Cloud storage connectors (GDrive / Dropbox / Box / SharePoint) with webhook triggers.

TODO: configure credentials —
  - GDRIVE_CREDENTIALS_JSON (service-account JSON)
  - DROPBOX_ACCESS_TOKEN
  - BOX_DEVELOPER_TOKEN
  - SHAREPOINT_CLIENT_ID / SHAREPOINT_CLIENT_SECRET
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from makepdf.web.auth import require_api_key


router = APIRouter(prefix="/api/cloud-storage", tags=["cloud-storage"])


class WebhookReg(BaseModel):
    provider: str  # gdrive | dropbox | box | sharepoint
    folder_id: Optional[str] = None
    callback_url: str


# In-memory webhook registrations.
_WEBHOOKS: List[Dict[str, Any]] = []


@router.post("/webhooks/register")
async def register_webhook(payload: WebhookReg, api_key: Optional[str] = Depends(require_api_key)):
    _WEBHOOKS.append({"id": len(_WEBHOOKS) + 1, **payload.dict()})
    return {"ok": True, "registered": _WEBHOOKS[-1]}


@router.get("/webhooks")
async def list_webhooks(api_key: Optional[str] = Depends(require_api_key)):
    return {"count": len(_WEBHOOKS), "webhooks": _WEBHOOKS}


@router.get("/list")
async def list_files(provider: str, folder_id: Optional[str] = None,
                     api_key: Optional[str] = Depends(require_api_key)):
    if provider == "dropbox":
        token = os.environ.get("DROPBOX_ACCESS_TOKEN")
        if not token:
            raise HTTPException(503, "DROPBOX_ACCESS_TOKEN not configured")
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                "https://api.dropboxapi.com/2/files/list_folder",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"path": folder_id or ""},
            )
            return r.json()
    if provider == "box":
        token = os.environ.get("BOX_DEVELOPER_TOKEN")
        if not token:
            raise HTTPException(503, "BOX_DEVELOPER_TOKEN not configured")
        url = f"https://api.box.com/2.0/folders/{folder_id or '0'}/items"
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, headers={"Authorization": f"Bearer {token}"})
            return r.json()
    raise HTTPException(400, f"provider {provider} not yet implemented")


@router.post("/import-url")
async def import_url(payload: Dict[str, Any], api_key: Optional[str] = Depends(require_api_key)):
    """Generic 'download a URL into the makepdf working folder' helper."""
    url = payload.get("url")
    name = payload.get("name", "imported.pdf")
    if not url:
        raise HTTPException(400, "url required")
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.get(url)
        if r.status_code != 200:
            raise HTTPException(502, f"download failed: {r.status_code}")
        # Stash temp file path; persisting to canonical storage is project-specific.
        from pathlib import Path
        from tempfile import gettempdir
        out = Path(gettempdir()) / name
        out.write_bytes(r.content)
        return {"saved": str(out), "bytes": len(r.content)}
