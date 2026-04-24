"""Routes for PDF flattening: forms, annotations, or all."""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from makepdf.config import TEMP_DIR
from makepdf.core.flatten import flatten_forms, flatten_annotations, flatten_all
from makepdf.web.shared import templates

router = APIRouter(prefix="/flatten", tags=["flatten"])


async def _save_upload(upload: UploadFile, suffix: str = ".pdf") -> Path:
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


@router.get("", response_class=HTMLResponse)
async def flatten_page(request: Request):
    return templates.TemplateResponse("flatten.html", {"request": request})


@router.post("/forms")
async def flatten_forms_route(
    pdf_file: UploadFile = File(...),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = flatten_forms(src, output=Path(out_tmp))
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="flattened_forms.pdf",
        )
    finally:
        src.unlink(missing_ok=True)


@router.post("/annotations")
async def flatten_annotations_route(
    pdf_file: UploadFile = File(...),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = flatten_annotations(src, output=Path(out_tmp))
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="flattened_annotations.pdf",
        )
    finally:
        src.unlink(missing_ok=True)


@router.post("/all")
async def flatten_all_route(
    pdf_file: UploadFile = File(...),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = flatten_all(src, output=Path(out_tmp))
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="flattened.pdf",
        )
    finally:
        src.unlink(missing_ok=True)
