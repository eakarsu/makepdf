"""Routes for merge, split, and extract-pages operations."""

import io
import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from makepdf.config import TEMP_DIR
from makepdf.core.merger import extract_pages, merge, split
from makepdf.web.shared import templates

router = APIRouter(tags=["merge"])


async def _save_upload(upload: UploadFile, suffix: str = ".pdf") -> Path:
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


@router.get("/merge", response_class=HTMLResponse)
async def merge_page(request: Request):
    return templates.TemplateResponse("merge.html", {"request": request})


@router.post("/merge")
async def merge_pdfs(
    pdf_files: list[UploadFile] = File(...),
):
    saved: list[Path] = []
    try:
        for f in pdf_files:
            saved.append(await _save_upload(f, ".pdf"))

        fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
        os.close(fd)

        result = merge(saved, output=Path(out_tmp))
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="merged.pdf",
        )
    finally:
        for p in saved:
            p.unlink(missing_ok=True)


@router.post("/split")
async def split_pdf(
    pdf_file: UploadFile = File(...),
    ranges: str = Form(...),
):
    """Split a PDF. Ranges format: '1-3,4-6,7-10' (1-indexed, inclusive)."""
    src = await _save_upload(pdf_file, ".pdf")
    split_dir = Path(tempfile.mkdtemp(dir=str(TEMP_DIR)))

    try:
        page_ranges: list[tuple[int, int]] = []
        for part in ranges.split(","):
            part = part.strip()
            if "-" in part:
                start_s, end_s = part.split("-", 1)
                page_ranges.append((int(start_s.strip()), int(end_s.strip())))
            else:
                n = int(part)
                page_ranges.append((n, n))

        results = split(src, page_ranges, output_dir=split_dir)

        # Package split files into a zip
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in results:
                zf.write(p, p.name)
        zip_buf.seek(0)

        return StreamingResponse(
            zip_buf,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=split_pdfs.zip"},
        )
    finally:
        src.unlink(missing_ok=True)
        import shutil
        shutil.rmtree(split_dir, ignore_errors=True)


@router.post("/extract-pages")
async def extract_pages_route(
    pdf_file: UploadFile = File(...),
    pages: str = Form(...),
):
    """Extract specific pages. Format: '1,3,5' (1-indexed)."""
    src = await _save_upload(pdf_file, ".pdf")

    try:
        page_list = [int(p.strip()) for p in pages.split(",") if p.strip()]

        fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
        os.close(fd)

        result = extract_pages(src, page_list, output=Path(out_tmp))
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="extracted_pages.pdf",
        )
    finally:
        src.unlink(missing_ok=True)
