"""Routes for digital signature operations on PDFs."""

import io
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from makepdf.config import TEMP_DIR
from makepdf.web.shared import templates

router = APIRouter(prefix="/sign", tags=["sign"])


async def _save_upload(upload: UploadFile, suffix: str = ".pdf") -> Path:
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


@router.get("", response_class=HTMLResponse)
async def sign_page(request: Request):
    return templates.TemplateResponse("sign.html", {"request": request})


@router.post("/add-signature")
async def add_signature(
    pdf_file: UploadFile = File(...),
    signature_image: UploadFile = File(...),
    page_num: int = Form(0),
    x: float = Form(72),
    y: float = Form(72),
    width: float = Form(200),
    height: float = Form(80),
):
    """Add a visual signature image to a PDF page."""
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas

    src = await _save_upload(pdf_file, ".pdf")
    sig_suffix = Path(signature_image.filename or "sig.png").suffix or ".png"
    sig_path = await _save_upload(signature_image, sig_suffix)
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        reader = PdfReader(str(src))
        writer = PdfWriter()

        for i, page in enumerate(reader.pages):
            if i == page_num:
                page_box = page.mediabox
                pw = float(page_box.width)
                ph = float(page_box.height)

                buf = io.BytesIO()
                c = canvas.Canvas(buf, pagesize=(pw, ph))
                c.drawImage(
                    str(sig_path), x, y,
                    width=width, height=height,
                    mask="auto", preserveAspectRatio=True,
                )
                c.save()
                buf.seek(0)

                overlay = PdfReader(buf).pages[0]
                page.merge_page(overlay)

            writer.add_page(page)

        with open(out_tmp, "wb") as f:
            writer.write(f)

        return FileResponse(
            path=out_tmp,
            media_type="application/pdf",
            filename="signed.pdf",
        )
    finally:
        src.unlink(missing_ok=True)
        sig_path.unlink(missing_ok=True)


@router.post("/verify")
async def verify_signature(
    pdf_file: UploadFile = File(...),
):
    """Check whether a PDF contains digital signature fields.

    This performs a basic structural check -- it looks for signature field
    entries in the PDF's AcroForm.  Full cryptographic verification requires
    the ``pyHanko`` library.
    """
    from pypdf import PdfReader

    src = await _save_upload(pdf_file, ".pdf")

    try:
        reader = PdfReader(str(src))
        sig_fields = []

        fields = reader.get_fields()
        if fields:
            for name, field_obj in fields.items():
                ft = str(field_obj.get("/FT", ""))
                if ft == "/Sig":
                    value = field_obj.get("/V")
                    sig_fields.append({
                        "name": name,
                        "signed": value is not None,
                    })

        if sig_fields:
            return JSONResponse(content={
                "has_signatures": True,
                "fields": sig_fields,
            })
        else:
            return JSONResponse(content={
                "has_signatures": False,
                "fields": [],
                "message": "No digital signature fields found in this PDF.",
            })
    finally:
        src.unlink(missing_ok=True)
