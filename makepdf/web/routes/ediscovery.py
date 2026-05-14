"""Bates-numbering + redaction copilot for legal e-discovery."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from makepdf.web.auth import require_api_key
from makepdf.web.ai_helpers import call_openrouter, parse_ai_json


router = APIRouter(prefix="/api/ediscovery", tags=["ediscovery"])


class PrivilegeReq(BaseModel):
    document_text: str
    matter_keywords: Optional[List[str]] = None


class BatesPlanReq(BaseModel):
    doc_titles: List[str]
    prefix: str = "DEF"
    start: int = 1
    digits: int = 6


@router.post("/privilege-flag")
async def privilege_flag(req: PrivilegeReq, api_key: Optional[str] = Depends(require_api_key)):
    if not req.document_text:
        raise HTTPException(400, "document_text required")
    system = (
        "You analyse e-discovery documents for attorney-client privilege and work product. "
        "Return JSON: {\"privileged\":bool,\"confidence\":0-1,\"basis\":[string],"
        "\"redaction_suggestions\":[{\"text\":string,\"reason\":string}]}."
    )
    user = (
        f"Matter keywords: {req.matter_keywords or []}\n\n"
        f"Document:\n{req.document_text[:6000]}"
    )
    raw = call_openrouter(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=900,
        temperature=0.0,
    )
    return parse_ai_json(raw) or {"raw": raw}


@router.post("/bates-plan")
async def bates_plan(req: BatesPlanReq, api_key: Optional[str] = Depends(require_api_key)):
    out: List[Dict[str, Any]] = []
    n = req.start
    for title in req.doc_titles:
        label = f"{req.prefix}-{str(n).zfill(req.digits)}"
        out.append({"document": title, "bates": label})
        n += 1
    return {"count": len(out), "labels": out, "next_index": n}
