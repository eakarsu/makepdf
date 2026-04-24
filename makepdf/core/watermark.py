"""Watermark functionality for PDFs — text and image overlays."""

import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf, ensure_path, output_path


def add_text_watermark(
    input_pdf: str | Path,
    text: str,
    output: str | Path | None = None,
    opacity: float = 0.3,
    angle: float = 45,
    font_size: int = 60,
    color: tuple[float, float, float] = (0.5, 0.5, 0.5),
) -> Path:
    """Add diagonal text watermark on every page.

    Creates a reportlab overlay with semi-transparent rotated text centered on
    each page, then merges the overlay onto every page using pypdf.
    """
    pdf_path = ensure_pdf(input_pdf)
    out = output_path(output, pdf_path.stem + "_watermarked.pdf")
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()

    for page in reader.pages:
        page_box = page.mediabox
        page_width = float(page_box.width)
        page_height = float(page_box.height)

        # Build overlay PDF in memory
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(page_width, page_height))
        c.saveState()
        c.setFillColorRGB(*color)
        c.setFillAlpha(opacity)
        c.setFont("Helvetica-Bold", font_size)

        # Move to center, rotate, draw text centered
        c.translate(page_width / 2, page_height / 2)
        c.rotate(angle)
        c.drawCentredString(0, 0, text)

        c.restoreState()
        c.save()
        buf.seek(0)

        overlay_page = PdfReader(buf).pages[0]
        page.merge_page(overlay_page)
        writer.add_page(page)

    with open(out, "wb") as f:
        writer.write(f)

    return out


def add_image_watermark(
    input_pdf: str | Path,
    image_path: str | Path,
    output: str | Path | None = None,
    opacity: float = 0.3,
    position: str = "center",
    scale: float = 0.5,
) -> Path:
    """Add image watermark on every page.

    Parameters
    ----------
    position : str
        One of ``"center"``, ``"top-left"``, ``"top-right"``,
        ``"bottom-left"``, ``"bottom-right"``.
    scale : float
        Scale relative to page size (0.0–1.0).
    """
    valid_positions = {"center", "top-left", "top-right", "bottom-left", "bottom-right"}
    if position not in valid_positions:
        raise InputError(
            f"Invalid position '{position}'. Must be one of {sorted(valid_positions)}"
        )

    pdf_path = ensure_pdf(input_pdf)
    img_path = ensure_path(image_path)
    out = output_path(output, pdf_path.stem + "_watermarked.pdf")

    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()

    # Get image dimensions via reportlab utility
    from reportlab.lib.utils import ImageReader as RLImageReader

    rl_img = RLImageReader(str(img_path))
    img_orig_w, img_orig_h = rl_img.getSize()

    for page in reader.pages:
        page_box = page.mediabox
        page_width = float(page_box.width)
        page_height = float(page_box.height)

        # Scale image relative to page width, preserving aspect ratio
        img_w = page_width * scale
        img_h = img_w * (img_orig_h / img_orig_w)

        # If scaled height exceeds page, clamp to page height instead
        if img_h > page_height * scale:
            img_h = page_height * scale
            img_w = img_h * (img_orig_w / img_orig_h)

        # Compute position
        margin = 0.25 * inch
        if position == "center":
            x = (page_width - img_w) / 2
            y = (page_height - img_h) / 2
        elif position == "top-left":
            x = margin
            y = page_height - img_h - margin
        elif position == "top-right":
            x = page_width - img_w - margin
            y = page_height - img_h - margin
        elif position == "bottom-left":
            x = margin
            y = margin
        elif position == "bottom-right":
            x = page_width - img_w - margin
            y = margin

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(page_width, page_height))
        c.saveState()
        c.setFillAlpha(opacity)
        c.drawImage(
            str(img_path),
            x,
            y,
            width=img_w,
            height=img_h,
            mask="auto",
            preserveAspectRatio=True,
        )
        c.restoreState()
        c.save()
        buf.seek(0)

        overlay_page = PdfReader(buf).pages[0]
        page.merge_page(overlay_page)
        writer.add_page(page)

    with open(out, "wb") as f:
        writer.write(f)

    return out
