"""POST /api/ai-fill-form — LLM-mapped form filling.

Given a blank PDF form (with AcroForm fields) and a JSON ``source`` of
arbitrary key/value data (e.g. structured patient data, an extracted invoice,
or a free-form blob), ask the LLM to map source fields to form field names,
then call ``core.forms.fill_form`` deterministically.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from makepdf.config import TEMP_DIR
from makepdf.core.forms import extract_form_data, fill_form
from makepdf.web.auth import require_api_key
from makepdf.web.ai_helpers import (
    DEFAULT_MODEL,
    ai_rate_limiter,
    call_openrouter,
    parse_ai_json,
    persist_ai_result,
)

router = APIRouter(prefix="/api", tags=["ai"])


async def _save_upload(upload: UploadFile) -> Path:
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


@router.post("/ai-fill-form", dependencies=[Depends(ai_rate_limiter)])
async def ai_fill_form(
    pdf_file: UploadFile = File(..., description="PDF with AcroForm fields"),
    source_json: str = Form(..., description="JSON object with source data"),
    preview: bool = Form(False, description="Return mapping only — do not write filled PDF"),
    api_key: str | None = Depends(require_api_key),
):
    """Fill the form fields of ``pdf_file`` using the AI-derived mapping from
    ``source_json``.
    """
    api_openrouter = os.getenv("OPENROUTER_API_KEY")
    if not api_openrouter:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY not configured.")

    try:
        source = json.loads(source_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="source_json is not valid JSON.")

    t0 = time.time()
    src = await _save_upload(pdf_file)
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)
    out_path = Path(out_tmp)

    try:
        # 1. Discover form fields
        try:
            form_fields = extract_form_data(src)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"PDF has no AcroForm: {e}") from e

        if not form_fields:
            raise HTTPException(status_code=422, detail="PDF contains no fillable form fields.")

        # 2. Ask the LLM for a mapping
        prompt = f"""You are an intelligent form-filling assistant. Map the source data fields to the form field names.

Form field names (with current values):
{json.dumps(form_fields, indent=2, default=str)}

Source data:
{json.dumps(source, indent=2, default=str)}

Respond ONLY with JSON in this format:
{{"mapping": {{"form_field_name_1": "value from source", "form_field_name_2": "value"}},
  "skipped": ["form_field_3 - no source value"],
  "confidence": 0.95}}

Only include form fields you can populate. Use the EXACT form field names as keys."""

        raw = call_openrouter(
            [{"role": "user", "content": prompt}],
            api_key=api_openrouter,
            temperature=0.0,
        )
        try:
            parsed = parse_ai_json(raw)
            if not isinstance(parsed, dict):
                raise ValueError("expected object")
        except ValueError as e:
            persist_ai_result(
                feature="ai-fill-form",
                input_payload={"formFieldCount": len(form_fields)},
                output_payload={"raw": raw[:500]},
                api_key=api_key,
                success=False,
                error_message=str(e),
                latency_ms=int((time.time() - t0) * 1000),
            )
            raise HTTPException(status_code=502, detail=f"AI returned non-JSON mapping: {e}") from e

        mapping = parsed.get("mapping", {}) or {}
        # Filter to actual form field names only
        valid_mapping = {k: str(v) for k, v in mapping.items() if k in form_fields}

        if preview:
            preview_body = {
                "mapping": valid_mapping,
                "skipped": parsed.get("skipped", []),
                "confidence": parsed.get("confidence", None),
                "model": DEFAULT_MODEL,
                "formFieldCount": len(form_fields),
            }
            persist_ai_result(
                feature="ai-fill-form-preview",
                input_payload={"formFieldCount": len(form_fields)},
                output_payload=preview_body,
                api_key=api_key,
                success=True,
                latency_ms=int((time.time() - t0) * 1000),
            )
            return JSONResponse(content=preview_body)

        # 3. Deterministic fill via core.forms
        try:
            written = fill_form(src, valid_mapping, out_path)
        except Exception as e:
            persist_ai_result(
                feature="ai-fill-form",
                input_payload={"formFieldCount": len(form_fields), "mapped": len(valid_mapping)},
                output_payload=None,
                api_key=api_key,
                success=False,
                error_message=str(e),
                latency_ms=int((time.time() - t0) * 1000),
            )
            raise HTTPException(status_code=500, detail=f"fill_form failed: {e}") from e

        persist_ai_result(
            feature="ai-fill-form",
            input_payload={"formFieldCount": len(form_fields), "mapped": len(valid_mapping)},
            output_payload={"output": str(written), "mapping": valid_mapping},
            api_key=api_key,
            success=True,
            latency_ms=int((time.time() - t0) * 1000),
        )
        return FileResponse(
            path=str(written),
            media_type="application/pdf",
            filename="ai_filled_form.pdf",
        )
    finally:
        src.unlink(missing_ok=True)
