"""Routes for PDF transformations: compress, watermark, headers/footers, encrypt/decrypt."""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from makepdf.config import TEMP_DIR
from makepdf.core.encryption import decrypt, encrypt
from makepdf.core.headers_footers import add_headers_footers
from makepdf.core.watermark import add_image_watermark, add_text_watermark
from makepdf.web.shared import templates

router = APIRouter(prefix="/transform", tags=["transform"])


async def _save_upload(upload: UploadFile, suffix: str = ".pdf") -> Path:
    fd, tmp = tempfile.mkstemp(suffix=suffix, dir=str(TEMP_DIR))
    os.close(fd)
    p = Path(tmp)
    p.write_bytes(await upload.read())
    return p


@router.get("", response_class=HTMLResponse)
async def transform_page(request: Request):
    return templates.TemplateResponse("transform.html", {"request": request})


@router.post("/compress")
async def compress_pdf(
    pdf_file: UploadFile = File(...),
):
    """Compress a PDF by rewriting it with pypdf's compress_content_streams."""
    from pypdf import PdfReader, PdfWriter

    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        reader = PdfReader(str(src))
        writer = PdfWriter()
        for page in reader.pages:
            page.compress_content_streams()
            writer.add_page(page)
        if reader.metadata:
            writer.add_metadata(reader.metadata)
        with open(out_tmp, "wb") as f:
            writer.write(f)

        return FileResponse(
            path=out_tmp,
            media_type="application/pdf",
            filename="compressed.pdf",
        )
    finally:
        src.unlink(missing_ok=True)


@router.post("/watermark/text")
async def watermark_text(
    pdf_file: UploadFile = File(...),
    text: str = Form(...),
    opacity: float = Form(0.3),
    angle: float = Form(45),
    font_size: int = Form(60),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = add_text_watermark(
            src, text,
            output=Path(out_tmp),
            opacity=opacity,
            angle=angle,
            font_size=font_size,
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="watermarked.pdf",
        )
    finally:
        src.unlink(missing_ok=True)


@router.post("/watermark/image")
async def watermark_image(
    pdf_file: UploadFile = File(...),
    image_file: UploadFile = File(...),
    opacity: float = Form(0.3),
    position: str = Form("center"),
    scale: float = Form(0.5),
):
    src = await _save_upload(pdf_file, ".pdf")
    img_suffix = Path(image_file.filename or "img.png").suffix or ".png"
    img_path = await _save_upload(image_file, img_suffix)
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = add_image_watermark(
            src, img_path,
            output=Path(out_tmp),
            opacity=opacity,
            position=position,
            scale=scale,
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="watermarked.pdf",
        )
    finally:
        src.unlink(missing_ok=True)
        img_path.unlink(missing_ok=True)


@router.post("/headers-footers")
async def headers_footers(
    pdf_file: UploadFile = File(...),
    header_left: str = Form(""),
    header_center: str = Form(""),
    header_right: str = Form(""),
    footer_left: str = Form(""),
    footer_center: str = Form(""),
    footer_right: str = Form(""),
    font: str = Form("Helvetica"),
    font_size: int = Form(10),
    start_page: int = Form(1),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = add_headers_footers(
            src,
            output=Path(out_tmp),
            header_left=header_left,
            header_center=header_center,
            header_right=header_right,
            footer_left=footer_left,
            footer_center=footer_center,
            footer_right=footer_right,
            font=font,
            font_size=font_size,
            start_page=start_page,
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="with_headers_footers.pdf",
        )
    finally:
        src.unlink(missing_ok=True)


@router.post("/encrypt")
async def encrypt_pdf(
    pdf_file: UploadFile = File(...),
    user_password: str = Form(...),
    owner_password: str = Form(""),
    allow_printing: bool = Form(True),
    allow_copying: bool = Form(True),
    allow_modifying: bool = Form(False),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        owner_pwd = owner_password if owner_password else None
        result = encrypt(
            src,
            output=Path(out_tmp),
            user_password=user_password,
            owner_password=owner_pwd,
            allow_printing=allow_printing,
            allow_copying=allow_copying,
            allow_modifying=allow_modifying,
        )
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="encrypted.pdf",
        )
    finally:
        src.unlink(missing_ok=True)


@router.post("/decrypt")
async def decrypt_pdf(
    pdf_file: UploadFile = File(...),
    password: str = Form(...),
):
    src = await _save_upload(pdf_file, ".pdf")
    fd, out_tmp = tempfile.mkstemp(suffix=".pdf", dir=str(TEMP_DIR))
    os.close(fd)

    try:
        result = decrypt(src, output=Path(out_tmp), password=password)
        return FileResponse(
            path=str(result),
            media_type="application/pdf",
            filename="decrypted.pdf",
        )
    finally:
        src.unlink(missing_ok=True)
