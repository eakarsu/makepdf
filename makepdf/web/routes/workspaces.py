"""Team workspaces with shared templates and approval flows."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from makepdf.web.auth import require_api_key


router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class Workspace(BaseModel):
    name: str
    owner_email: str


class Template(BaseModel):
    workspace_id: str
    name: str
    body: str  # markdown / html template
    approver_email: Optional[str] = None


class Approval(BaseModel):
    template_id: str
    approver_email: str
    decision: str  # approve | reject
    note: Optional[str] = None


_WORKSPACES: Dict[str, Dict[str, Any]] = {}
_TEMPLATES: Dict[str, Dict[str, Any]] = {}
_APPROVALS: List[Dict[str, Any]] = []


@router.post("")
def create_workspace(w: Workspace, api_key: Optional[str] = Depends(require_api_key)):
    wid = f"ws_{int(time.time()*1000)}"
    _WORKSPACES[wid] = {"id": wid, **w.dict(), "members": [w.owner_email], "created_at": time.time()}
    return _WORKSPACES[wid]


@router.get("")
def list_workspaces(api_key: Optional[str] = Depends(require_api_key)):
    return {"count": len(_WORKSPACES), "workspaces": list(_WORKSPACES.values())}


@router.post("/{wid}/members")
def add_member(wid: str, payload: Dict[str, Any], api_key: Optional[str] = Depends(require_api_key)):
    w = _WORKSPACES.get(wid)
    if not w:
        raise HTTPException(404, "workspace not found")
    email = payload.get("email")
    if not email:
        raise HTTPException(400, "email required")
    if email not in w["members"]:
        w["members"].append(email)
    return w


@router.post("/templates")
def add_template(t: Template, api_key: Optional[str] = Depends(require_api_key)):
    if t.workspace_id not in _WORKSPACES:
        raise HTTPException(404, "workspace not found")
    tid = f"tpl_{int(time.time()*1000)}"
    _TEMPLATES[tid] = {"id": tid, **t.dict(), "status": "draft" if t.approver_email else "approved", "created_at": time.time()}
    return _TEMPLATES[tid]


@router.get("/{wid}/templates")
def list_templates(wid: str, api_key: Optional[str] = Depends(require_api_key)):
    return {"templates": [t for t in _TEMPLATES.values() if t["workspace_id"] == wid]}


@router.post("/approvals")
def approve(a: Approval, api_key: Optional[str] = Depends(require_api_key)):
    t = _TEMPLATES.get(a.template_id)
    if not t:
        raise HTTPException(404, "template not found")
    t["status"] = "approved" if a.decision == "approve" else "rejected"
    _APPROVALS.append({**a.dict(), "at": time.time()})
    return {"template": t, "approval_count": len(_APPROVALS)}
