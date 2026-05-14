"""Multi-language OCR + AI translation chained as one job.

Reuses the existing OCR routes via direct module import where possible; falls
back to an LLM round-trip when an OCR text payload is supplied directly.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from makepdf.web.auth import require_api_key
from makepdf.web.ai_helpers import call_openrouter, parse_ai_json


router = APIRouter(prefix="/api/ocr-translate", tags=["ocr-translate"])


class TranslateReq(BaseModel):
    text: str
    source_language: Optional[str] = "auto"
    target_language: str = "en"
    preserve_formatting: bool = True


class ChainedReq(BaseModel):
    ocr_text: str
    source_language: Optional[str] = "auto"
    target_languages: List[str]


@router.post("/translate")
async def translate(req: TranslateReq, api_key: Optional[str] = Depends(require_api_key)):
    if not req.text:
        raise HTTPException(400, "text required")
    system = (
        f"Translate from {req.source_language or 'auto-detected language'} to {req.target_language}. "
        + ("Preserve line breaks and headings." if req.preserve_formatting else "")
        + " Return JSON {\"text\":string,\"detected_source\":string}."
    )
    raw = call_openrouter(
        [{"role": "system", "content": system}, {"role": "user", "content": req.text[:8000]}],
        max_tokens=2000,
        temperature=0.2,
    )
    return parse_ai_json(raw) or {"text": raw}


@router.post("/chain")
async def chain(req: ChainedReq, api_key: Optional[str] = Depends(require_api_key)):
    """Translate a single OCR'd text into multiple target languages in one call."""
    if not req.ocr_text:
        raise HTTPException(400, "ocr_text required")
    if not req.target_languages:
        raise HTTPException(400, "target_languages required")
    out: Dict[str, Any] = {"source_language": req.source_language, "translations": {}}
    for tl in req.target_languages[:6]:
        system = f"Translate from {req.source_language or 'auto'} into {tl}. Return only the translated text."
        translated = call_openrouter(
            [{"role": "system", "content": system}, {"role": "user", "content": req.ocr_text[:6000]}],
            max_tokens=2000,
            temperature=0.2,
        )
        out["translations"][tl] = translated
    return out
