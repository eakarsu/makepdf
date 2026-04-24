"""Routes for OCR operations on PDFs."""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from makepdf.config import TEMP_DIR
from makepdf.web.shared import templates

router = APIRouter(prefix="/ocr", tags=["ocr"])


async def _save_upload(upload: UploadFile, suffix: str = ".pdf") -> Path:
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


@router.get("", response_class=HTMLResponse)
async def ocr_page(request: Request):
    return templates.TemplateResponse("ocr.html", {"request": request})


@router.post("/extract-text")
async def ocr_extract_text(
    pdf_file: UploadFile = File(...),
    language: str = Form("eng"),
):
    """Run OCR on a scanned PDF and extract text.

    Requires pytesseract and pdf2image to be installed.
    """
    src = await _save_upload(pdf_file, ".pdf")

    try:
        try:
            import pytesseract
            from pdf2image import convert_from_path
        except ImportError:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "OCR requires pytesseract and pdf2image. "
                    "Install with: pip install pytesseract pdf2image"
                },
            )

        images = convert_from_path(str(src))
        text_parts = []
        for i, img in enumerate(images, 1):
            text = pytesseract.image_to_string(img, lang=language)
            text_parts.append(f"--- Page {i} ---\n{text}")

        return JSONResponse(content={"text": "\n\n".join(text_parts)})
    finally:
        src.unlink(missing_ok=True)


@router.post("/make-searchable")
async def ocr_make_searchable(
    pdf_file: UploadFile = File(...),
    language: str = Form("eng"),
):
    """Create a searchable PDF by overlaying OCR text on the original.

    Requires pytesseract, pdf2image, and reportlab.
    """
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        try:
            import pytesseract
            from pdf2image import convert_from_path
        except ImportError:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "OCR requires pytesseract and pdf2image. "
                    "Install with: pip install pytesseract pdf2image"
                },
            )

        import io

        from pypdf import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas

        images = convert_from_path(str(src))
        reader = PdfReader(str(src))
        writer = PdfWriter()

        for i, (page, img) in enumerate(zip(reader.pages, images)):
            page_box = page.mediabox
            pw = float(page_box.width)
            ph = float(page_box.height)

            # Run OCR with bounding box data
            ocr_data = pytesseract.image_to_data(
                img, lang=language, output_type=pytesseract.Output.DICT
            )

            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=(pw, ph))
            c.setFillAlpha(0)  # invisible text

            img_w, img_h = img.size
            scale_x = pw / img_w
            scale_y = ph / img_h

            for j in range(len(ocr_data["text"])):
                word = ocr_data["text"][j].strip()
                if not word:
                    continue
                x = ocr_data["left"][j] * scale_x
                # PDF y is from bottom; image y is from top
                y = ph - (ocr_data["top"][j] + ocr_data["height"][j]) * scale_y
                fs = max(ocr_data["height"][j] * scale_y * 0.8, 4)

                c.setFont("Helvetica", fs)
                c.drawString(x, y, word)

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
            filename="searchable.pdf",
        )
    finally:
        src.unlink(missing_ok=True)
