"""Routes for PDF attachments: add, list, and extract attachments."""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

from makepdf.config import TEMP_DIR
from makepdf.core.attachments import add_attachment, list_attachments, extract_attachments
from makepdf.web.shared import templates

router = APIRouter(prefix="/attach", tags=["attach"])


async def _save_upload(upload: UploadFile, suffix: str = ".pdf") -> Path:
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


@router.get("", response_class=HTMLResponse)
async def attach_page(request: Request):
    return templates.TemplateResponse("attach.html", {"request": request})


@router.post("/add")
async def attach_add(
    pdf_file: UploadFile = File(...),
    attachment: UploadFile = File(...),
    description: str = Form(""),
):
    src = await _save_upload(pdf_file, ".pdf")
    att_suffix = Path(attachment.filename or "file.bin").suffix or ".bin"
    att_path = await _save_upload(attachment, att_suffix)
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = add_attachment(
            src,
            output=Path(out_tmp),
            attachment=att_path,
            filename=attachment.filename or "attachment",
            description=description,
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="with_attachment.pdf",
        )
    finally:
        src.unlink(missing_ok=True)
        att_path.unlink(missing_ok=True)


@router.post("/list")
async def attach_list(
    pdf_file: UploadFile = File(...),
):
    src = await _save_upload(pdf_file, ".pdf")

    try:
        result = list_attachments(src)
        return JSONResponse(content=result)
    finally:
        src.unlink(missing_ok=True)


@router.post("/extract")
async def attach_extract(
    pdf_file: UploadFile = File(...),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".zip", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = extract_attachments(src, output=Path(out_tmp))
        return StreamingResponse(
            open(str(result), "rb"),
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=attachments.zip"},
        )
    finally:
        src.unlink(missing_ok=True)
