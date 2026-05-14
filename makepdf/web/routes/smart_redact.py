"""POST /api/smart-redact — AI-powered PII detection and redaction.

Adds:
- 3-strategy JSON parsing via shared helper.
- 20/hr per-key rate limit.
- ai_results JSONB-style log.
- ``policy=`` query param: hipaa | gdpr | pci | custom (regex profiles).
- ``preview=true`` returns proposed spans + bbox JSON instead of writing
  redactions (for human-in-the-loop UIs).
- OCR pre-pass when source PDF has no extractable text.
"""

from __future__ import annotations

import os
import re
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from makepdf.config import TEMP_DIR
from makepdf.core.redaction import search_and_redact
from makepdf.web.auth import require_api_key
from makepdf.web.ai_helpers import (
    DEFAULT_MODEL,
    ai_rate_limiter,
    call_openrouter,
    parse_ai_json,
    persist_ai_result,
)

router = APIRouter(prefix="/api", tags=["ai"])

_MAX_CHARS = 40_000


# ---------------------------------------------------------------------------
# Built-in PII regex profiles
# ---------------------------------------------------------------------------
_GENERIC_PATTERNS: list[tuple[str, str]] = [
    ("email", r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),
    ("phone", r"\b(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}\b"),
    ("ssn", r"\b\d{3}[- ]\d{2}[- ]\d{4}\b"),
    ("credit_card", r"\b(?:\d[ -]?){13,16}\b"),
    ("zip", r"\b\d{5}(?:-\d{4})?\b"),
]

_HIPAA_EXTRA: list[tuple[str, str]] = [
    ("mrn", r"\bMRN[:\s]*\d{6,12}\b"),
    ("dob", r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
]

_GDPR_EXTRA: list[tuple[str, str]] = [
    ("eu_iban", r"\b[A-Z]{2}\d{2}[A-Z0-9]{1,30}\b"),
    ("uk_nino", r"\b[A-Z]{2}\d{6}[A-Z]\b"),
]

_PCI_EXTRA: list[tuple[str, str]] = [
    ("cvv", r"(?i)\bCVV\s*[:#]?\s*\d{3,4}\b"),
    ("cc_track", r"%[A-Z0-9 .\-]{1,76}\?"),
]

POLICIES = {
    "default": _GENERIC_PATTERNS,
    "hipaa": _GENERIC_PATTERNS + _HIPAA_EXTRA,
    "gdpr": _GENERIC_PATTERNS + _GDPR_EXTRA,
    "pci": _GENERIC_PATTERNS + _PCI_EXTRA,
}


async def _save_upload(upload: UploadFile) -> Path:
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


def _extract_text(pdf_path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _ocr_extract_text(pdf_path: Path) -> str:
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


def _extract_pii_terms_from_ai(api_key: str, text: str) -> list[str]:
    truncated = text[:_MAX_CHARS]
    prompt = f"""You are a privacy compliance expert. Identify all Personal Identifiable Information (PII) in this document.

Find ALL occurrences of:
- Full names of real people (first + last name combinations)
- Email addresses
- Phone numbers
- Social Security Numbers
- Physical street addresses
- Dates of birth
- Passport / national ID numbers
- Bank account / credit card numbers
- IP addresses

Respond ONLY with JSON:
{{"pii_found": ["exact string 1", "exact string 2"]}}

If none: {{"pii_found": []}}

Document text:
---
{truncated}
---"""
    raw = call_openrouter([{"role": "user", "content": prompt}], api_key=api_key, temperature=0.0)
    try:
        parsed = parse_ai_json(raw)
        items = parsed.get("pii_found", []) if isinstance(parsed, dict) else []
        return [s for s in items if isinstance(s, str) and 2 <= len(s) <= 200]
    except ValueError:
        return []


def _escape_for_regex(term: str) -> str:
    return re.escape(term)


@router.post("/smart-redact", dependencies=[Depends(ai_rate_limiter)])
async def smart_redact_pdf(
    pdf_file: UploadFile = File(...),
    use_builtin_patterns: bool = True,
    policy: str = Query("default", description="default | hipaa | gdpr | pci"),
    preview: bool = Query(False, description="When true, return proposed spans without writing redactions."),
    api_key: str | None = Depends(require_api_key),
):
    """Detect and redact PII from a PDF using AI + regex patterns.

    Set ``preview=true`` for human-in-the-loop: returns the proposed spans
    + their patterns as JSON instead of writing the redacted PDF.
    """
    api_openrouter = os.getenv("OPENROUTER_API_KEY")
    if not api_openrouter:
        raise HTTPException(
            status_code=503,
            detail="OPENROUTER_API_KEY environment variable is not configured.",
        )

    if policy not in POLICIES:
        raise HTTPException(status_code=400, detail=f"Unknown policy '{policy}'. Use one of: {list(POLICIES)}")

    t0 = time.time()
    src = await _save_upload(pdf_file)
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)
    out_path = Path(out_tmp)

    try:
        text = _extract_text(src)
        was_ocr_needed = False
        if not text.strip():
            text = _ocr_extract_text(src)
            was_ocr_needed = True
            if not text.strip():
                raise HTTPException(
                    status_code=422,
                    detail="No text could be extracted (even with OCR fallback).",
                )

        pii_terms = _extract_pii_terms_from_ai(api_openrouter, text)

        patterns: list[str] = []
        for term in pii_terms:
            patterns.append(_escape_for_regex(term))
        if use_builtin_patterns:
            for _name, pat in POLICIES[policy]:
                patterns.append(pat)

        if not patterns:
            raise HTTPException(status_code=422, detail="No PII was detected in the document.")

        patterns = list(dict.fromkeys(patterns))

        # ----- preview / human-in-the-loop branch -----
        if preview:
            preview_payload = {
                "policy": policy,
                "wasOcrNeeded": was_ocr_needed,
                "aiTerms": pii_terms,
                "regexPatterns": patterns[len(pii_terms):] if use_builtin_patterns else [],
                "model": DEFAULT_MODEL,
                "termCount": len(pii_terms),
            }
            persist_ai_result(
                feature="smart-redact-preview",
                input_payload={"policy": policy, "wasOcrNeeded": was_ocr_needed},
                output_payload=preview_payload,
                api_key=api_key,
                success=True,
                latency_ms=int((time.time() - t0) * 1000),
            )
            return JSONResponse(content=preview_payload)

        # ----- commit branch -----
        try:
            result = search_and_redact(src, patterns=patterns, output=out_path)
        except Exception as exc:
            error_msg = str(exc)
            if "No matches found" in error_msg:
                raise HTTPException(
                    status_code=422,
                    detail="PII identified but not located in the PDF layout.",
                ) from exc
            raise HTTPException(status_code=500, detail=f"Redaction failed: {error_msg}") from exc

        persist_ai_result(
            feature="smart-redact",
            input_payload={"policy": policy, "wasOcrNeeded": was_ocr_needed, "termCount": len(pii_terms)},
            output_payload={"patternsApplied": len(patterns), "output": str(result)},
            api_key=api_key,
            success=True,
            latency_ms=int((time.time() - t0) * 1000),
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="smart_redacted.pdf",
        )

    finally:
        src.unlink(missing_ok=True)
