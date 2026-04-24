"""Routes for PDF links: add hyperlinks and extract existing links."""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from makepdf.config import TEMP_DIR
from makepdf.core.links import add_link, extract_links
from makepdf.web.shared import templates

router = APIRouter(prefix="/link", tags=["link"])


async def _save_upload(upload: UploadFile, suffix: str = ".pdf") -> Path:
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


@router.get("", response_class=HTMLResponse)
async def link_page(request: Request):
    return templates.TemplateResponse("link.html", {"request": request})


@router.post("/add")
async def link_add(
    pdf_file: UploadFile = File(...),
    page_num: int = Form(...),
    x: float = Form(...),
    y: float = Form(...),
    width: float = Form(...),
    height: float = Form(...),
    url: str = Form(...),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = add_link(
            src,
            output=Path(out_tmp),
            page_num=page_num,
            x=x,
            y=y,
            width=width,
            height=height,
            url=url,
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="with_link.pdf",
        )
    finally:
        src.unlink(missing_ok=True)


@router.post("/extract")
async def link_extract(
    pdf_file: UploadFile = File(...),
):
    src = await _save_upload(pdf_file, ".pdf")

    try:
        result = extract_links(src)
        return JSONResponse(content=result)
    finally:
        src.unlink(missing_ok=True)
