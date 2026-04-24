"""Routes for PDF optimization: optimize file size and generate reports."""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from makepdf.config import TEMP_DIR
from makepdf.core.optimizer import optimize, get_optimization_report
from makepdf.web.shared import templates

router = APIRouter(prefix="/optimize", tags=["optimize"])


async def _save_upload(upload: UploadFile, suffix: str = ".pdf") -> Path:
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


@router.get("", response_class=HTMLResponse)
async def optimize_page(request: Request):
    return templates.TemplateResponse("optimize.html", {"request": request})


@router.post("/run")
async def optimize_run(
    pdf_file: UploadFile = File(...),
    remove_duplication: bool = Form(True),
    remove_metadata: bool = Form(False),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = optimize(
            src,
            output=Path(out_tmp),
            remove_duplication=remove_duplication,
            remove_metadata=remove_metadata,
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="optimized.pdf",
        )
    finally:
        src.unlink(missing_ok=True)


@router.post("/report")
async def optimize_report(
    pdf_file: UploadFile = File(...),
):
    src = await _save_upload(pdf_file, ".pdf")

    try:
        result = get_optimization_report(src)
        return JSONResponse(content=result)
    finally:
        src.unlink(missing_ok=True)
