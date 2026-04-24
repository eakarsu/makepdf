"""Routes for extracting text and images from PDFs."""

import io
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from makepdf.config import TEMP_DIR
from makepdf.core.image_extractor import extract_images
from makepdf.core.text_extractor import extract_text, extract_text_by_page
from makepdf.web.shared import templates

router = APIRouter(prefix="/extract", tags=["extract"])


async def _save_upload(upload: UploadFile, suffix: str = ".pdf") -> Path:
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


@router.get("", response_class=HTMLResponse)
async def extract_page(request: Request):
    return templates.TemplateResponse("extract.html", {"request": request})


@router.post("/text")
async def extract_text_route(
    pdf_file: UploadFile = File(...),
    by_page: bool = Form(False),
):
    """Extract text from a PDF. Returns JSON with text content."""
    src = await _save_upload(pdf_file, ".pdf")

    try:
        if by_page:
            pages_text = extract_text_by_page(src)
            # Convert int keys to strings for JSON
            data = {str(k): v for k, v in pages_text.items()}
            return JSONResponse(content={"pages": data})
        else:
            text = extract_text(src)
            return JSONResponse(content={"text": text})
    finally:
        src.unlink(missing_ok=True)


@router.post("/images")
async def extract_images_route(
    pdf_file: UploadFile = File(...),
):
    """Extract all images from a PDF. Returns a zip file."""
    src = await _save_upload(pdf_file, ".pdf")
    img_dir = Path(tempfile.mkdtemp(dir=str(TEMP_DIR)))

    try:
        image_paths = extract_images(src, output_dir=img_dir)

        if not image_paths:
            return JSONResponse(
                content={"message": "No images found in the PDF."},
                status_code=200,
            )

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in image_paths:
                zf.write(p, p.name)
        zip_buf.seek(0)

        return StreamingResponse(
            zip_buf,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=extracted_images.zip"},
        )
    finally:
        src.unlink(missing_ok=True)
        shutil.rmtree(img_dir, ignore_errors=True)
