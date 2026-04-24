"""Routes for PDF stamps: preset stamps and custom text stamps."""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from makepdf.config import TEMP_DIR
from makepdf.core.stamps import add_stamp, add_custom_stamp
from makepdf.web.shared import templates

router = APIRouter(prefix="/stamp", tags=["stamp"])


async def _save_upload(upload: UploadFile, suffix: str = ".pdf") -> Path:
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


@router.get("", response_class=HTMLResponse)
async def stamp_page(request: Request):
    return templates.TemplateResponse("stamp.html", {"request": request})


@router.post("/add")
async def stamp_add(
    pdf_file: UploadFile = File(...),
    stamp_type: str = Form(...),
    position: str = Form("center"),
    opacity: float = Form(0.5),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = add_stamp(
            src,
            output=Path(out_tmp),
            stamp_type=stamp_type,
            position=position,
            opacity=opacity,
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="stamped.pdf",
        )
    finally:
        src.unlink(missing_ok=True)


@router.post("/custom")
async def stamp_custom(
    pdf_file: UploadFile = File(...),
    text: str = Form(...),
    font_size: int = Form(36),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = add_custom_stamp(
            src,
            output=Path(out_tmp),
            text=text,
            font_size=font_size,
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="stamped.pdf",
        )
    finally:
        src.unlink(missing_ok=True)
