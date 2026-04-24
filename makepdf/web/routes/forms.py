"""Routes for PDF form operations -- fill, extract, and list fields."""

import json
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from makepdf.config import TEMP_DIR
from makepdf.core.forms import create_form, extract_form_data, fill_form, list_form_fields
from makepdf.web.shared import templates

router = APIRouter(prefix="/forms", tags=["forms"])


async def _save_upload(upload: UploadFile, suffix: str = ".pdf") -> Path:
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


@router.get("", response_class=HTMLResponse)
async def forms_page(request: Request):
    return templates.TemplateResponse("forms.html", {"request": request})


@router.post("/create")
async def create_form_route(
    fields_json: str = Form(...),
    page_size: str = Form("A4"),
):
    """Create a PDF with form fields. fields_json is a JSON array of field defs."""
    fields = json.loads(fields_json)

    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    result = create_form(fields, output=Path(out_tmp), page_size=page_size)
    return FileResponse(
        path=str(result),
        media_type="application/pdf",
        filename="form.pdf",
    )


@router.post("/fill")
async def fill_form_route(
    pdf_file: UploadFile = File(...),
    data_json: str = Form(...),
):
    """Fill form fields. data_json is a JSON object {field_name: value}."""
    src = await _save_upload(pdf_file, ".pdf")
    data = json.loads(data_json)

    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = fill_form(src, data, output=Path(out_tmp))
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="filled_form.pdf",
        )
    finally:
        src.unlink(missing_ok=True)


@router.post("/extract")
async def extract_form_data_route(
    pdf_file: UploadFile = File(...),
):
    """Extract form field values as JSON."""
    src = await _save_upload(pdf_file, ".pdf")

    try:
        data = extract_form_data(src)
        return JSONResponse(content={"fields": data})
    finally:
        src.unlink(missing_ok=True)


@router.post("/list-fields")
async def list_fields_route(
    pdf_file: UploadFile = File(...),
):
    """List all form field names and types."""
    src = await _save_upload(pdf_file, ".pdf")

    try:
        fields = list_form_fields(src)
        return JSONResponse(content={"fields": fields})
    finally:
        src.unlink(missing_ok=True)
