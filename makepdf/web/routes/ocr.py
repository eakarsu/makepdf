"""OCR page plus redirects away from unsafe synchronous native execution."""

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse

from makepdf.web.shared import templates

router = APIRouter(prefix="/ocr", tags=["ocr"])


@router.get("", response_class=HTMLResponse)
async def ocr_page(request: Request):
    return templates.TemplateResponse("ocr.html", {"request": request})


@router.post("/extract-text")
async def ocr_extract_text(
    pdf_file: UploadFile = File(...),
    language: str = Form("eng"),
):
    """Require the durable queue and resource-limited worker."""
    raise HTTPException(
        status_code=410,
        detail="Synchronous native OCR is disabled. Use POST /api/ocr/extract-text/async.",
    )


@router.post("/make-searchable")
async def ocr_make_searchable(
    pdf_file: UploadFile = File(...),
    language: str = Form("eng"),
):
    """Require the durable queue and resource-limited worker."""
    raise HTTPException(
        status_code=410,
        detail="Synchronous native OCR is disabled. Use POST /api/ocr/make-searchable/async.",
    )
