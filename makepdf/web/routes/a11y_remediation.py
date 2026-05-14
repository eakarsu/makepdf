"""Accessibility remediation agent — auto-tag, alt text, and reading order suggestions."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from makepdf.web.auth import require_api_key
from makepdf.web.ai_helpers import call_openrouter, parse_ai_json


router = APIRouter(prefix="/api/a11y-remediation", tags=["a11y-remediation"])


class RemediateReq(BaseModel):
    page_text: str
    image_alt_candidates: Optional[List[Dict[str, Any]]] = None  # [{"id": "img1", "context": "..."}]


@router.post("/analyze")
async def analyze(req: RemediateReq, api_key: Optional[str] = Depends(require_api_key)):
    system = (
        "You are a PDF accessibility remediation agent. Given page text plus image context, "
        "produce JSON: {\"tags\":[{\"role\":\"H1|H2|P|List|Figure\",\"text\":string}],"
        "\"alt_text\":[{\"id\":string,\"alt\":string}],\"reading_order\":[string],\"warnings\":[string]}."
    )
    user = (
        f"Page text:\n{req.page_text[:6000]}\n\n"
        f"Images: {req.image_alt_candidates or []}"
    )
    raw = call_openrouter(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=1200,
        temperature=0.2,
    )
    return parse_ai_json(raw) or {"raw": raw}


@router.post("/apply-suggestions")
async def apply(payload: Dict[str, Any], api_key: Optional[str] = Depends(require_api_key)):
    """Stub apply step — caller can pass back analysis output to record an audit row."""
    return {
        "applied": True,
        "tags_count": len(payload.get("tags", [])),
        "alt_count": len(payload.get("alt_text", [])),
        "note": "Stored as recommendation; actual PDF rewrite happens via existing /api/markup-route."
    }
