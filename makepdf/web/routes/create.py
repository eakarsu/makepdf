"""Routes for PDF creation from text, HTML, Markdown, and images."""

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from makepdf.config import TEMP_DIR
from makepdf.core.creator import from_html, from_images, from_markdown, from_text
from makepdf.web.shared import templates

router = APIRouter(prefix="/create", tags=["create"])


@router.get("", response_class=HTMLResponse)
async def create_page(request: Request):
    return templates.TemplateResponse("create.html", {"request": request})


@router.post("/text")
async def create_from_text(
    text: str = Form(...),
    font: str = Form("Helvetica"),
    font_size: int = Form(12),
    page_size: str = Form("A4"),
):
    import os
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)
    out_path = Path(tmp)

    result = from_text(text, output=out_path, font=font, font_size=font_size, page_size=page_size)
    return FileResponse(
        path=str(result),
        media_type="application/pdf",
        filename="created.pdf",
        background=None,
    )


@router.post("/html")
async def create_from_html(
    html_text: str = Form(None),
    html_file: UploadFile = File(None),
    page_size: str = Form("A4"),
):
    if html_file and html_file.filename:
        content = (await html_file.read()).decode("utf-8")
    elif html_text:
        content = html_text
    else:
        return {"error": "Provide either html_text or html_file"}

    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    import os
    os.close(fd)

    result = from_html(content, output=Path(tmp), page_size=page_size)
    return FileResponse(
        path=str(result),
        media_type="application/pdf",
        filename="created_from_html.pdf",
    )


@router.post("/markdown")
async def create_from_markdown(
    md_text: str = Form(None),
    md_file: UploadFile = File(None),
    page_size: str = Form("A4"),
):
    if md_file and md_file.filename:
        content = (await md_file.read()).decode("utf-8")
    elif md_text:
        content = md_text
    else:
        return {"error": "Provide either md_text or md_file"}

    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    import os
    os.close(fd)

    result = from_markdown(content, output=Path(tmp), page_size=page_size)
    return FileResponse(
        path=str(result),
        media_type="application/pdf",
        filename="created_from_markdown.pdf",
    )


@router.post("/images")
async def create_from_images(
    images: list[UploadFile] = File(...),
    page_size: str = Form("A4"),
):
    import os

    image_paths = []
    try:
        for img in images:
            suffix = Path(img.filename or "image.png").suffix or ".png"
            fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
            os.close(fd)
            tmp_path = Path(tmp)
            tmp_path.write_bytes(await img.read())
            image_paths.append(tmp_path)

        fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
        os.close(fd)

        result = from_images(image_paths, output=Path(out_tmp), page_size=page_size)
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="created_from_images.pdf",
        )
    finally:
        for p in image_paths:
            p.unlink(missing_ok=True)
