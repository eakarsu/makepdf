"""Routes for PDF cropping: crop pages, resize, and trim margins."""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from makepdf.config import TEMP_DIR
from makepdf.core.cropper import crop_pages, resize_pages, trim_margins
from makepdf.web.shared import templates

router = APIRouter(prefix="/crop", tags=["crop"])


async def _save_upload(upload: UploadFile, suffix: str = ".pdf") -> Path:
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


@router.get("", response_class=HTMLResponse)
async def crop_page(request: Request):
    return templates.TemplateResponse("crop.html", {"request": request})


@router.post("/pages")
async def crop_pages_route(
    pdf_file: UploadFile = File(...),
    left: float = Form(...),
    bottom: float = Form(...),
    right: float = Form(...),
    top: float = Form(...),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = crop_pages(
            src,
            output=Path(out_tmp),
            left=left,
            bottom=bottom,
            right=right,
            top=top,
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="cropped.pdf",
        )
    finally:
        src.unlink(missing_ok=True)


@router.post("/resize")
async def resize_pages_route(
    pdf_file: UploadFile = File(...),
    width: float = Form(...),
    height: float = Form(...),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = resize_pages(
            src,
            output=Path(out_tmp),
            width=width,
            height=height,
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="resized.pdf",
        )
    finally:
        src.unlink(missing_ok=True)


@router.post("/trim")
async def trim_margins_route(
    pdf_file: UploadFile = File(...),
    margin: float = Form(...),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = trim_margins(
            src,
            output=Path(out_tmp),
            margin=margin,
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="trimmed.pdf",
        )
    finally:
        src.unlink(missing_ok=True)
