"""Routes for PDF redaction: area-based and text-based redaction."""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from makepdf.config import TEMP_DIR
from makepdf.core.redaction import redact_area, redact_text
from makepdf.web.shared import templates

router = APIRouter(prefix="/redact", tags=["redact"])


async def _save_upload(upload: UploadFile, suffix: str = ".pdf") -> Path:
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


@router.get("", response_class=HTMLResponse)
async def redact_page(request: Request):
    return templates.TemplateResponse("redact.html", {"request": request})


@router.post("/area")
async def redact_area_route(
    pdf_file: UploadFile = File(...),
    page_num: int = Form(...),
    x: float = Form(...),
    y: float = Form(...),
    width: float = Form(...),
    height: float = Form(...),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = redact_area(
            src,
            output=Path(out_tmp),
            page_num=page_num,
            x=x,
            y=y,
            width=width,
            height=height,
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="redacted.pdf",
        )
    finally:
        src.unlink(missing_ok=True)


@router.post("/text")
async def redact_text_route(
    pdf_file: UploadFile = File(...),
    search_term: str = Form(...),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = redact_text(
            src,
            output=Path(out_tmp),
            search_term=search_term,
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="redacted.pdf",
        )
    finally:
        src.unlink(missing_ok=True)
