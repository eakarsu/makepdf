"""Routes for Bates numbering."""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from makepdf.config import TEMP_DIR
from makepdf.core.bates import add_bates_numbers
from makepdf.web.shared import templates

router = APIRouter(prefix="/bates", tags=["bates"])


async def _save_upload(upload: UploadFile, suffix: str = ".pdf") -> Path:
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


@router.get("", response_class=HTMLResponse)
async def bates_page(request: Request):
    return templates.TemplateResponse("bates.html", {"request": request})


@router.post("/add")
async def bates_add(
    pdf_file: UploadFile = File(...),
    prefix: str = Form(""),
    suffix: str = Form(""),
    start: int = Form(1),
    digits: int = Form(6),
    position: str = Form("bottom-center"),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = add_bates_numbers(
            src,
            output=Path(out_tmp),
            prefix=prefix,
            suffix=suffix,
            start=start,
            digits=digits,
            position=position,
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="bates_numbered.pdf",
        )
    finally:
        src.unlink(missing_ok=True)
