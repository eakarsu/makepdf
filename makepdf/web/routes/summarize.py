"""POST /api/summarize — LLM-powered PDF summarization via OpenRouter."""

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

_MAX_CHARS = 40_000  # ~10k tokens — keep cost low


async def _save_upload(upload: UploadFile) -> Path:
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


def _extract_text(pdf_path: Path) -> str:
    """Extract plain text from a PDF using pypdf."""
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _ocr_extract_text(pdf_path: Path) -> str:
    """OCR-based fallback for image-based PDFs. Returns empty string when OCR isn't available."""
    try:
        # Lazy import — OCR is an optional extra
        from makepdf.core import ocr as ocr_mod
        return ocr_mod.extract_text(pdf_path)  # type: ignore[attr-defined]
    except Exception:
        try:
            import pytesseract
            from pdf2image import convert_from_path
        except ImportError:
            return ""
        try:
            images = convert_from_path(str(pdf_path), dpi=200)
            return "\n\n".join(pytesseract.image_to_string(img) for img in images)
        except Exception:
            return ""


def _parse_summary_response(raw: str) -> dict:
    """Parse the LLM text response using the shared 3-strategy JSON parser."""
    try:
        parsed = parse_ai_json(raw)
        if isinstance(parsed, dict):
            return parsed
    except ValueError:
        pass
    return {
        "summary": raw.strip(),
        "keyPoints": [],
        "entities": [],
    }


@router.post("/summarize", dependencies=[Depends(ai_rate_limiter)])
async def summarize_pdf(
    pdf_file: UploadFile = File(...),
    api_key: str | None = Depends(require_api_key),
):
    """Extract text from a PDF and return an LLM-generated executive summary.

    If pypdf returns no text the route automatically falls back to OCR (when
    pytesseract / pdf2image are installed).
    """
    api_openrouter = os.getenv("OPENROUTER_API_KEY")
    if not api_openrouter:
        raise HTTPException(
            status_code=503,
            detail="OPENROUTER_API_KEY environment variable is not configured.",
        )

    t0 = time.time()
    src = await _save_upload(pdf_file)
    was_ocr_needed = False
    truncated_signal = False
    text = ""
    try:
        text = _extract_text(src)
        if not text.strip():
            text = _ocr_extract_text(src)
            was_ocr_needed = True
    finally:
        src.unlink(missing_ok=True)

    if not text.strip():
        raise HTTPException(status_code=422, detail="No text could be extracted from the PDF.")

    word_count = len(text.split())
    if len(text) > _MAX_CHARS:
        truncated_signal = True
    truncated = text[:_MAX_CHARS]

    prompt = f"""You are a professional document analyst. Analyze the following PDF document text and produce a structured JSON response.

Respond ONLY with valid JSON in this exact format:
{{
  "summary": "A 2-4 sentence executive summary of the document",
  "keyPoints": ["Key point 1", "Key point 2", "Key point 3"],
  "entities": ["Person/Org/Place 1", "Person/Org/Place 2"]
}}

Document text:
---
{truncated}
---"""

    try:
        raw_response = call_openrouter(
            [{"role": "user", "content": prompt}],
            api_key=api_openrouter,
            temperature=0.2,
        )
    except HTTPException:
        persist_ai_result(
            feature="summarize",
            input_payload={"wordCount": word_count, "wasOcrNeeded": was_ocr_needed},
            output_payload=None,
            api_key=api_key,
            success=False,
            error_message="OpenRouter call failed",
            latency_ms=int((time.time() - t0) * 1000),
        )
        raise

    parsed = _parse_summary_response(raw_response)
    body = {
        "summary": parsed.get("summary", ""),
        "keyPoints": parsed.get("keyPoints", []),
        "entities": parsed.get("entities", []),
        "wordCount": word_count,
        "wasOcrNeeded": was_ocr_needed,
        "wasTextTruncated": truncated_signal,
        "model": DEFAULT_MODEL,
    }
    persist_ai_result(
        feature="summarize",
        input_payload={"wordCount": word_count, "wasOcrNeeded": was_ocr_needed},
        output_payload=body,
        api_key=api_key,
        success=True,
        latency_ms=int((time.time() - t0) * 1000),
    )
    return JSONResponse(content=body)
