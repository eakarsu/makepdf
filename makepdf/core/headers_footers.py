"""Add headers and footers to PDF pages."""

import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf, output_path


def add_headers_footers(
    input_pdf: str | Path,
    output: str | Path | None = None,
    header_left: str = "",
    header_center: str = "",
    header_right: str = "",
    footer_left: str = "",
    footer_center: str = "",
    footer_right: str = "",
    font: str = "Helvetica",
    font_size: int = 10,
    start_page: int = 1,
) -> Path:
    """Add headers and footers to every page of a PDF.

    Supported placeholders in any header/footer string:

    * ``{page}``  — current page number (1-based)
    * ``{total}`` — total number of pages

    Parameters
    ----------
    start_page : int
        First page (1-based) on which headers/footers should appear.
        Pages before *start_page* are copied unchanged.
    """
    pdf_path = ensure_pdf(input_pdf)
    out = output_path(output, pdf_path.stem + "_hf.pdf")

    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    total_pages = len(reader.pages)

    margin_x = 0.5 * inch
    header_y_offset = 0.4 * inch  # distance from top edge
    footer_y_offset = 0.4 * inch  # distance from bottom edge

    for page_index, page in enumerate(reader.pages):
        page_num = page_index + 1

        # Pages before start_page pass through unmodified
        if page_num < start_page:
            writer.add_page(page)
            continue

        page_box = page.mediabox
        page_width = float(page_box.width)
        page_height = float(page_box.height)

        # Resolve placeholders
        replacements = {"{page}": str(page_num), "{total}": str(total_pages)}

        def _resolve(text: str) -> str:
            result = text
            for placeholder, value in replacements.items():
                result = result.replace(placeholder, value)
            return result

        hl = _resolve(header_left)
        hc = _resolve(header_center)
        hr = _resolve(header_right)
        fl = _resolve(footer_left)
        fc = _resolve(footer_center)
        fr = _resolve(footer_right)

        # Build overlay
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(page_width, page_height))
        c.setFont(font, font_size)

        header_y = page_height - header_y_offset
        footer_y = footer_y_offset

        # Header
        if hl:
            c.drawString(margin_x, header_y, hl)
        if hc:
            c.drawCentredString(page_width / 2, header_y, hc)
        if hr:
            c.drawRightString(page_width - margin_x, header_y, hr)

        # Footer
        if fl:
            c.drawString(margin_x, footer_y, fl)
        if fc:
            c.drawCentredString(page_width / 2, footer_y, fc)
        if fr:
            c.drawRightString(page_width - margin_x, footer_y, fr)

        c.save()
        buf.seek(0)

        overlay_page = PdfReader(buf).pages[0]
        page.merge_page(overlay_page)
        writer.add_page(page)

    with open(out, "wb") as f:
        writer.write(f)

    return out
