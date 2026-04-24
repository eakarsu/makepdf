"""Routes for PDF accessibility: set language and check accessibility."""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from makepdf.config import TEMP_DIR
from makepdf.core.accessibility import set_language, check_accessibility
from makepdf.web.shared import templates

router = APIRouter(prefix="/a11y", tags=["a11y"])


async def _save_upload(upload: UploadFile, suffix: str = ".pdf") -> Path:
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


@router.get("", response_class=HTMLResponse)
async def a11y_page(request: Request):
    return templates.TemplateResponse("a11y.html", {"request": request})


@router.post("/set-language")
async def a11y_set_language(
    pdf_file: UploadFile = File(...),
    language: str = Form(...),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = set_language(
            src,
            output=Path(out_tmp),
            language=language,
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="accessible.pdf",
        )
    finally:
        src.unlink(missing_ok=True)


@router.post("/check")
async def a11y_check(
    pdf_file: UploadFile = File(...),
):
    src = await _save_upload(pdf_file, ".pdf")

    try:
        result = check_accessibility(src)
        return JSONResponse(content=result)
    finally:
        src.unlink(missing_ok=True)
