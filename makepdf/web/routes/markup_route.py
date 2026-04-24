"""Routes for PDF markup: highlights and sticky notes."""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from makepdf.config import TEMP_DIR
from makepdf.core.markup import highlight_area, add_sticky_note
from makepdf.web.shared import templates

router = APIRouter(prefix="/markup", tags=["markup"])


async def _save_upload(upload: UploadFile, suffix: str = ".pdf") -> Path:
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


@router.get("", response_class=HTMLResponse)
async def markup_page(request: Request):
    return templates.TemplateResponse("markup.html", {"request": request})


@router.post("/highlight")
async def markup_highlight(
    pdf_file: UploadFile = File(...),
    page_num: int = Form(0),
    x: float = Form(72),
    y: float = Form(700),
    width: float = Form(200),
    height: float = Form(20),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = highlight_area(
            src, page_num, x, y, width, height, Path(out_tmp),
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="highlighted.pdf",
        )
    finally:
        src.unlink(missing_ok=True)


@router.post("/note")
async def markup_note(
    pdf_file: UploadFile = File(...),
    page_num: int = Form(0),
    x: float = Form(200),
    y: float = Form(700),
    text: str = Form(...),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = add_sticky_note(
            src, page_num, x, y, text, Path(out_tmp),
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="annotated.pdf",
        )
    finally:
        src.unlink(missing_ok=True)
