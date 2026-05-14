"""POST /api/classify — classify a PDF by its first page text."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from makepdf.config import TEMP_DIR
from makepdf.web.auth import require_api_key
from makepdf.web.ai_helpers import (
    DEFAULT_MODEL,
    ai_rate_limiter,
    call_openrouter,
    parse_ai_json,
    persist_ai_result,
)

router = APIRouter(prefix="/api", tags=["ai"])

_LABELS = ["contract", "invoice", "resume", "medical", "court_filing", "report", "manual", "letter", "other"]
_MAX_CHARS = 10_000


async def _save_upload(upload: UploadFile) -> Path:
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


def _extract_first_pages_text(pdf_path: Path, max_pages: int = 2) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(pdf_path))
    chunks = []
    for page in reader.pages[:max_pages]:
        t = page.extract_text()
        if t:
            chunks.append(t)
    return "\n\n".join(chunks)


@router.post("/classify", dependencies=[Depends(ai_rate_limiter)])
async def classify_pdf(
    pdf_file: UploadFile = File(...),
    api_key: str | None = Depends(require_api_key),
):
    """Classify a PDF into one of: contract, invoice, resume, medical, court_filing,
    report, manual, letter, other. Returns label + confidence + suggested_pipeline.
    """
    api_openrouter = os.getenv("OPENROUTER_API_KEY")
    if not api_openrouter:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY not configured.")

    t0 = time.time()
    src = await _save_upload(pdf_file)
    try:
        text = _extract_first_pages_text(src)
    finally:
        src.unlink(missing_ok=True)

    if not text.strip():
        raise HTTPException(status_code=422, detail="No text extractable for classification.")

    truncated = text[:_MAX_CHARS]
    prompt = f"""You are a document classification assistant. Tag this document with ONE label from:
{", ".join(_LABELS)}

Respond ONLY with JSON:
{{"label":"invoice","confidence":0.92,"reasoning":"Has line items + total + invoice number","suggestedPipeline":["bates","redact"]}}

Document text (first pages):
---
{truncated}
---"""

    raw = call_openrouter([{"role": "user", "content": prompt}], api_key=api_openrouter, temperature=0.1)
    try:
        parsed = parse_ai_json(raw)
        if not isinstance(parsed, dict):
            raise ValueError("Expected object")
    except ValueError:
        parsed = {"label": "other", "confidence": 0.0, "reasoning": "parse failed", "suggestedPipeline": []}

    label = str(parsed.get("label", "other"))
    if label not in _LABELS:
        label = "other"

    body = {
        "label": label,
        "confidence": float(parsed.get("confidence", 0.0) or 0.0),
        "reasoning": str(parsed.get("reasoning", "")),
        "suggestedPipeline": list(parsed.get("suggestedPipeline", [])),
        "model": DEFAULT_MODEL,
    }

    persist_ai_result(
        feature="classify",
        input_payload={"chars": len(text)},
        output_payload=body,
        api_key=api_key,
        success=True,
        latency_ms=int((time.time() - t0) * 1000),
    )
    return JSONResponse(content=body)
