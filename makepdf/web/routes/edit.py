"""Routes for editing existing PDFs -- add text and images."""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from makepdf.config import TEMP_DIR
from makepdf.core.editor import add_image, add_text
from makepdf.web.shared import templates

router = APIRouter(prefix="/edit", tags=["edit"])


async def _save_upload(upload: UploadFile, suffix: str = ".pdf") -> Path:
    """Save an uploaded file to a temp location and return the path."""
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
    os.close(fd)
    tmp_path = Path(tmp)
    tmp_path.write_bytes(await upload.read())
    return tmp_path


@router.get("", response_class=HTMLResponse)
async def edit_page(request: Request):
    return templates.TemplateResponse("edit.html", {"request": request})


@router.post("/add-text")
async def edit_add_text(
    pdf_file: UploadFile = File(...),
    page_num: int = Form(0),
    x: float = Form(72),
    y: float = Form(700),
    text: str = Form(...),
    font: str = Form("Helvetica"),
    font_size: float = Form(12),
    color_r: float = Form(0),
    color_g: float = Form(0),
    color_b: float = Form(0),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = add_text(
            input_pdf=src,
            page_num=page_num,
            x=x,
            y=y,
            text=text,
            output=Path(out_tmp),
            font=font,
            font_size=font_size,
            color=(color_r, color_g, color_b),
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="edited.pdf",
        )
    finally:
        src.unlink(missing_ok=True)


@router.post("/add-image")
async def edit_add_image(
    pdf_file: UploadFile = File(...),
    image_file: UploadFile = File(...),
    page_num: int = Form(0),
    x: float = Form(72),
    y: float = Form(500),
    width: float = Form(None),
    height: float = Form(None),
):
    src = await _save_upload(pdf_file, ".pdf")
    img_suffix = Path(image_file.filename or "img.png").suffix or ".png"
    img_path = await _save_upload(image_file, img_suffix)
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        w = width if width and width > 0 else None
        h = height if height and height > 0 else None
        result = add_image(
            input_pdf=src,
            page_num=page_num,
            x=x,
            y=y,
            image_path=img_path,
            output=Path(out_tmp),
            width=w,
            height=h,
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="edited.pdf",
        )
    finally:
        src.unlink(missing_ok=True)
        img_path.unlink(missing_ok=True)
