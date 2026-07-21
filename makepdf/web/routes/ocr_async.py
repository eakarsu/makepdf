"""POST /api/ocr/async — Async OCR job submission with progress tracking.

Accepts a PDF upload, saves it, starts a background asyncio task, and
immediately returns a jobId.  The client then polls:

  GET /api/jobs/{jobId}          — status + result_url when done
  GET /api/jobs/{jobId}/progress — SSE stream of live progress events
  GET /api/jobs/{jobId}/download — download the result PDF
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from makepdf.config import OBJECT_DIR, TEMP_DIR
from makepdf.web.auth import Identity, require_identity
from makepdf.web.governance import consume_quota, delete_document, register_document
from makepdf.web.intake import save_upload
from makepdf.web.job_registry import Job, create_job, update_progress

router = APIRouter(prefix="/api/ocr", tags=["ocr", "jobs"])


# ---------------------------------------------------------------------------
# Background task implementations
# ---------------------------------------------------------------------------

async def _run_ocr_extract_text(src: Path, language: str, job: Job) -> Path:
    """OCR a PDF and write extracted text to a .txt file.  Reports progress."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise RuntimeError(
            "OCR requires pytesseract and pdf2image. "
            "Install with: pip install pytesseract pdf2image"
        ) from exc

    update_progress(job.id, 5, "Converting PDF pages to images")

    # Run blocking I/O in a thread pool to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    images = await loop.run_in_executor(None, lambda: convert_from_path(str(src)))

    total = len(images)
    text_parts: list[str] = []

    for i, img in enumerate(images, 1):
        stage = f"OCR page {i}/{total}"
        progress = 10 + int((i / total) * 85)
        update_progress(job.id, progress, stage)

        text = await loop.run_in_executor(
            None,
            lambda img=img: pytesseract.image_to_string(img, lang=language),
        )
        text_parts.append(f"--- Page {i} ---\n{text}")

    update_progress(job.id, 97, "Writing output file")

    fd, out_tmp = tempfile.mkstemp(suffix=".txt", dir=str(TEMP_DIR))
    os.close(fd)
    out_path = Path(out_tmp)
    out_path.write_text("\n\n".join(text_parts), encoding="utf-8")

    return out_path


async def _run_ocr_make_searchable(src: Path, language: str, job: Job) -> Path:
    """OCR a PDF and produce a searchable PDF with invisible text overlay."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise RuntimeError(
            "OCR requires pytesseract and pdf2image. "
            "Install with: pip install pytesseract pdf2image"
        ) from exc

    import io

    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas as rl_canvas

    loop = asyncio.get_event_loop()

    update_progress(job.id, 5, "Converting PDF pages to images")
    images = await loop.run_in_executor(None, lambda: convert_from_path(str(src)))

    reader = PdfReader(str(src))
    writer = PdfWriter()
    total = len(images)

    for i, (page, img) in enumerate(zip(reader.pages, images), 1):
        stage = f"OCR page {i}/{total}"
        progress = 10 + int((i / total) * 80)
        update_progress(job.id, progress, stage)

        page_box = page.mediabox
        pw = float(page_box.width)
        ph = float(page_box.height)

        ocr_data = await loop.run_in_executor(
            None,
            lambda img=img: pytesseract.image_to_data(
                img, lang=language, output_type=pytesseract.Output.DICT
            ),
        )

        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=(pw, ph))
        c.setFillAlpha(0)

        img_w, img_h = img.size
        scale_x = pw / img_w
        scale_y = ph / img_h

        for j in range(len(ocr_data["text"])):
            word = ocr_data["text"][j].strip()
            if not word:
                continue
            x = ocr_data["left"][j] * scale_x
            y = ph - (ocr_data["top"][j] + ocr_data["height"][j]) * scale_y
            fs = max(ocr_data["height"][j] * scale_y * 0.8, 4)
            c.setFont("Helvetica", fs)
            c.drawString(x, y, word)

        c.save()
        buf.seek(0)

        overlay = PdfReader(buf).pages[0]
        page.merge_page(overlay)
        writer.add_page(page)

    update_progress(job.id, 97, "Writing output PDF")

    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)
    out_path = Path(out_tmp)
    with open(out_path, "wb") as f:
        writer.write(f)

    return out_path


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/extract-text/async")
async def async_ocr_extract_text(
    pdf_file: UploadFile = File(...),
    language: str = Form("eng"),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=200),
    identity: Identity = Depends(require_identity),
):
    """Submit an async OCR text-extraction job.

    Returns immediately with ``{"jobId": "..."}`` while processing continues
    in the background.  Poll ``GET /api/jobs/{jobId}`` for status.
    """
    if not language.replace("+", "").replace("-", "").isalnum() or len(language) > 40:
        raise HTTPException(status_code=422, detail="Invalid OCR language selection.")
    intake = await save_upload(pdf_file, ".pdf", tenant_id=identity.tenant_id, durable=True)
    consume_quota(identity, uploaded_bytes=intake.size, jobs=1)
    document_id = register_document(identity, intake)
    payload = {
        "document_id": document_id,
        "source_path": str(intake.path),
        "source_sha256": intake.sha256,
        "language": language,
        "result_dir": str(OBJECT_DIR / identity.tenant_id),
    }
    try:
        job = create_job(
            tenant_id=identity.tenant_id, user_id=identity.user_id,
            kind="ocr-extract-text", payload=payload,
            idempotency_key=idempotency_key, filename="ocr_text.txt",
        )
    except ValueError as exc:
        delete_document(identity, document_id)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if job.payload.get("document_id") != document_id:
        delete_document(identity, document_id)

    return JSONResponse(
        status_code=202,
        content={
            "jobId": job.id,
            "status": job.status,
            "progress_url": f"/api/jobs/{job.id}/progress",
            "status_url": f"/api/jobs/{job.id}",
        },
    )


@router.post("/make-searchable/async")
async def async_ocr_make_searchable(
    pdf_file: UploadFile = File(...),
    language: str = Form("eng"),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=200),
    identity: Identity = Depends(require_identity),
):
    """Submit an async OCR make-searchable job.

    Returns immediately with ``{"jobId": "..."}`` while processing continues
    in the background.  Poll ``GET /api/jobs/{jobId}`` for status.
    """
    if not language.replace("+", "").replace("-", "").isalnum() or len(language) > 40:
        raise HTTPException(status_code=422, detail="Invalid OCR language selection.")
    intake = await save_upload(pdf_file, ".pdf", tenant_id=identity.tenant_id, durable=True)
    consume_quota(identity, uploaded_bytes=intake.size, jobs=1)
    document_id = register_document(identity, intake)
    payload = {
        "document_id": document_id,
        "source_path": str(intake.path),
        "source_sha256": intake.sha256,
        "language": language,
        "result_dir": str(OBJECT_DIR / identity.tenant_id),
    }
    try:
        job = create_job(
            tenant_id=identity.tenant_id, user_id=identity.user_id,
            kind="ocr-make-searchable", payload=payload,
            idempotency_key=idempotency_key, filename="searchable.pdf",
        )
    except ValueError as exc:
        delete_document(identity, document_id)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if job.payload.get("document_id") != document_id:
        delete_document(identity, document_id)

    return JSONResponse(
        status_code=202,
        content={
            "jobId": job.id,
            "status": job.status,
            "progress_url": f"/api/jobs/{job.id}/progress",
            "status_url": f"/api/jobs/{job.id}",
        },
    )
