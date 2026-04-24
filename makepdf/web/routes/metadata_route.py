"""Routes for PDF metadata: get and set document metadata."""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from makepdf.config import TEMP_DIR
from makepdf.core.metadata import get_metadata, set_metadata
from makepdf.web.shared import templates

router = APIRouter(prefix="/metadata", tags=["metadata"])


async def _save_upload(upload: UploadFile, suffix: str = ".pdf") -> Path:
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


@router.get("", response_class=HTMLResponse)
async def metadata_page(request: Request):
    return templates.TemplateResponse("metadata_page.html", {"request": request})


@router.post("/get")
async def metadata_get(
    pdf_file: UploadFile = File(...),
):
    src = await _save_upload(pdf_file, ".pdf")

    try:
        result = get_metadata(src)
        return JSONResponse(content=result)
    finally:
        src.unlink(missing_ok=True)


@router.post("/set")
async def metadata_set(
    pdf_file: UploadFile = File(...),
    title: str = Form(""),
    author: str = Form(""),
    subject: str = Form(""),
    keywords: str = Form(""),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = set_metadata(
            src,
            output=Path(out_tmp),
            title=title,
            author=author,
            subject=subject,
            keywords=keywords,
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="with_metadata.pdf",
        )
    finally:
        src.unlink(missing_ok=True)
