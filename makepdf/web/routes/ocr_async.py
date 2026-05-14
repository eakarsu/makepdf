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

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from makepdf.config import TEMP_DIR
from makepdf.web.auth import require_api_key
from makepdf.web.job_registry import Job, create_job, run_job, update_progress

router = APIRouter(prefix="/api/ocr", tags=["ocr", "jobs"])


async def _save_upload(upload: UploadFile, suffix: str = ".pdf") -> Path:
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


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

    src.unlink(missing_ok=True)
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

    src.unlink(missing_ok=True)
    return out_path


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/extract-text/async")
async def async_ocr_extract_text(
    pdf_file: UploadFile = File(...),
    language: str = Form("eng"),
    _auth: None = Depends(require_api_key),
):
    """Submit an async OCR text-extraction job.

    Returns immediately with ``{"jobId": "..."}`` while processing continues
    in the background.  Poll ``GET /api/jobs/{jobId}`` for status.
    """
    src = await _save_upload(pdf_file, ".pdf")

    job = create_job()
    job.extra["filename"] = "ocr_text.txt"

    async def _task(j: Job) -> Path:
        return await _run_ocr_extract_text(src, language, j)

    asyncio.create_task(run_job(job, _task))

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
    _auth: None = Depends(require_api_key),
):
    """Submit an async OCR make-searchable job.

    Returns immediately with ``{"jobId": "..."}`` while processing continues
    in the background.  Poll ``GET /api/jobs/{jobId}`` for status.
    """
    src = await _save_upload(pdf_file, ".pdf")

    job = create_job()
    job.extra["filename"] = "searchable.pdf"

    async def _task(j: Job) -> Path:
        return await _run_ocr_make_searchable(src, language, j)

    asyncio.create_task(run_job(job, _task))

    return JSONResponse(
        status_code=202,
        content={
            "jobId": job.id,
            "status": job.status,
            "progress_url": f"/api/jobs/{job.id}/progress",
            "status_url": f"/api/jobs/{job.id}",
        },
    )
