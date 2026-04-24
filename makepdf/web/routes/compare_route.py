"""Routes for PDF comparison: text diff and visual report."""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from makepdf.config import TEMP_DIR
from makepdf.core.compare import compare_text, generate_diff_report
from makepdf.web.shared import templates

router = APIRouter(prefix="/compare", tags=["compare"])


async def _save_upload(upload: UploadFile, suffix: str = ".pdf") -> Path:
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


@router.get("", response_class=HTMLResponse)
async def compare_page(request: Request):
    return templates.TemplateResponse("compare.html", {"request": request})


@router.post("/text")
async def compare_text_route(
    pdf_a: UploadFile = File(...),
    pdf_b: UploadFile = File(...),
):
    src_a = await _save_upload(pdf_a, ".pdf")
    src_b = await _save_upload(pdf_b, ".pdf")

    try:
        result = compare_text(src_a, src_b)
        return JSONResponse(content=result)
    finally:
        src_a.unlink(missing_ok=True)
        src_b.unlink(missing_ok=True)


@router.post("/report")
async def generate_diff_report_route(
    pdf_a: UploadFile = File(...),
    pdf_b: UploadFile = File(...),
):
    src_a = await _save_upload(pdf_a, ".pdf")
    src_b = await _save_upload(pdf_b, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = generate_diff_report(src_a, src_b, output=Path(out_tmp))
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="comparison_report.pdf",
        )
    finally:
        src_a.unlink(missing_ok=True)
        src_b.unlink(missing_ok=True)
