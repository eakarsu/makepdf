"""Administrative identity, audit, retention, and key-rotation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from makepdf.web.auth import Identity, create_api_key, require_identity, require_role, rotate_api_key
from makepdf.web.governance import billing_usage, delete_document, set_legal_hold
from makepdf.web.job_registry import list_audit

router = APIRouter(prefix="/api/governance", tags=["governance"])


class CreateKeyRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=120)
    role: str
    label: str = Field(min_length=1, max_length=120)
    expires_in_days: int = Field(default=90, ge=1, le=365)


@router.get("/me")
async def me(identity: Identity = Depends(require_identity)):
    return {"tenant_id": identity.tenant_id, "user_id": identity.user_id, "role": identity.role, "key_id": identity.key_id}


@router.post("/keys", status_code=201)
async def issue_key(payload: CreateKeyRequest, identity: Identity = Depends(require_identity)):
    require_role(identity, "administrator")
    try:
        key_id, raw_key = create_api_key(
            identity.tenant_id, payload.user_id, payload.role, payload.label,
            expires_in=payload.expires_in_days * 86400,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"key_id": key_id, "api_key": raw_key, "display_once": True}


@router.post("/keys/{key_id}/rotate", status_code=201)
async def rotate_key(key_id: str, identity: Identity = Depends(require_identity)):
    try:
        new_id, raw_key = rotate_api_key(identity, key_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Key not found.") from exc
    return {"key_id": new_id, "api_key": raw_key, "display_once": True}


@router.put("/documents/{document_id}/legal-hold")
async def legal_hold(document_id: str, enabled: bool = True, identity: Identity = Depends(require_identity)):
    set_legal_hold(identity, document_id, enabled)
    return {"document_id": document_id, "legal_hold": enabled}


@router.delete("/documents/{document_id}", status_code=202)
async def delete_owned_document(document_id: str, identity: Identity = Depends(require_identity)):
    delete_document(identity, document_id)
    return {"document_id": document_id, "status": "deleted"}


@router.get("/audit")
async def audit(limit: int = 100, identity: Identity = Depends(require_identity)):
    require_role(identity, "administrator", "auditor")
    return {"events": list_audit(identity.tenant_id, limit)}


@router.post("/billing/usage")
async def export_usage(day: str, identity: Identity = Depends(require_identity)):
    return billing_usage(identity, day)
