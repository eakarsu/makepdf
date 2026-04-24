"""PDF editing module – add text, images, shapes, and annotations to existing PDFs.

Uses reportlab to create transparent overlay pages, then merges them onto
existing pages with pypdf.
"""

import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color

from makepdf.config import DEFAULT_FONT, DEFAULT_FONT_SIZE
from makepdf.utils import ensure_pdf, output_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _page_dimensions(reader: PdfReader, page_num: int) -> tuple[float, float]:
    """Return (width, height) in points for the given page."""
    page = reader.pages[page_num]
    box = page.mediabox
    return float(box.width), float(box.height)


def _make_overlay(width: float, height: float) -> tuple[io.BytesIO, canvas.Canvas]:
    """Create a BytesIO-backed reportlab Canvas with the given dimensions."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width, height))
    return buf, c


def _merge_overlay(
    reader: PdfReader,
    page_num: int,
    overlay_buf: io.BytesIO,
    out_path: Path,
) -> Path:
    """Merge the overlay PDF onto *page_num* of *reader* and write to *out_path*."""
    overlay_reader = PdfReader(overlay_buf)
    writer = PdfWriter()

    for i, page in enumerate(reader.pages):
        if i == page_num:
            page.merge_page(overlay_reader.pages[0])
        writer.add_page(page)

    with open(out_path, "wb") as f:
        writer.write(f)

    return out_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_text(
    input_pdf: str | Path,
    page_num: int,
    x: float,
    y: float,
    text: str,
    output: str | Path | None,
    font: str = DEFAULT_FONT,
    font_size: float = DEFAULT_FONT_SIZE,
    color: tuple[float, float, float] = (0, 0, 0),
) -> Path:
    """Add *text* at position (*x*, *y*) on *page_num* of *input_pdf*.

    Parameters
    ----------
    input_pdf : path to the source PDF.
    page_num : zero-based page index.
    x, y : position in points from the lower-left corner.
    text : the string to render.
    output : destination path (``None`` → ``edited.pdf``).
    font : font family name (default ``Helvetica``).
    font_size : size in points (default 12).
    color : RGB tuple with components in 0-1 range.

    Returns
    -------
    Path to the written PDF.
    """
    src = ensure_pdf(input_pdf)
    dst = output_path(output, "edited.pdf")
    reader = PdfReader(str(src))

    w, h = _page_dimensions(reader, page_num)
    buf, c = _make_overlay(w, h)

    c.setFont(font, font_size)
    c.setFillColor(Color(*color))
    c.drawString(x, y, text)
    c.save()

    buf.seek(0)
    return _merge_overlay(reader, page_num, buf, dst)


def add_image(
    input_pdf: str | Path,
    page_num: int,
    x: float,
    y: float,
    image_path: str | Path,
    output: str | Path | None,
    width: float | None = None,
    height: float | None = None,
) -> Path:
    """Add an image at (*x*, *y*) on *page_num*.

    If only *width* or *height* is given the other dimension is calculated to
    preserve the original aspect ratio.  If neither is given the image is
    drawn at its intrinsic pixel size (1 px = 1 pt).

    Returns
    -------
    Path to the written PDF.
    """
    from reportlab.lib.utils import ImageReader

    src = ensure_pdf(input_pdf)
    img_path = Path(image_path)
    dst = output_path(output, "edited.pdf")
    reader = PdfReader(str(src))

    page_w, page_h = _page_dimensions(reader, page_num)
    buf, c = _make_overlay(page_w, page_h)

    img = ImageReader(str(img_path))
    iw, ih = img.getSize()  # intrinsic size in pixels

    if width is not None and height is not None:
        draw_w, draw_h = width, height
    elif width is not None:
        draw_w = width
        draw_h = ih * (width / iw)
    elif height is not None:
        draw_h = height
        draw_w = iw * (height / ih)
    else:
        draw_w, draw_h = float(iw), float(ih)

    c.drawImage(str(img_path), x, y, width=draw_w, height=draw_h, mask="auto")
    c.save()

    buf.seek(0)
    return _merge_overlay(reader, page_num, buf, dst)


def add_shape(
    input_pdf: str | Path,
    page_num: int,
    shape_type: str,
    output: str | Path | None,
    x: float = 0,
    y: float = 0,
    width: float = 100,
    height: float = 100,
    color: tuple[float, float, float] = (0, 0, 0),
    fill_color: tuple[float, float, float] | None = None,
) -> Path:
    """Draw a shape on *page_num*.

    Parameters
    ----------
    shape_type : ``"rect"``, ``"circle"``, or ``"line"``.
    x, y : lower-left anchor (or start point for lines).
    width, height : dimensions of the bounding box.
    color : stroke colour (RGB 0-1).
    fill_color : fill colour; ``None`` means no fill.

    Returns
    -------
    Path to the written PDF.
    """
    src = ensure_pdf(input_pdf)
    dst = output_path(output, "edited.pdf")
    reader = PdfReader(str(src))

    page_w, page_h = _page_dimensions(reader, page_num)
    buf, c = _make_overlay(page_w, page_h)

    c.setStrokeColor(Color(*color))
    if fill_color is not None:
        c.setFillColor(Color(*fill_color))
        do_fill = 1
    else:
        do_fill = 0

    shape_type = shape_type.lower().strip()

    if shape_type == "rect":
        c.rect(x, y, width, height, stroke=1, fill=do_fill)

    elif shape_type == "circle":
        # Treat (x, y) as the lower-left of the bounding box; derive centre
        # and radius from width/height (use the smaller dimension as diameter).
        radius = min(width, height) / 2
        cx = x + width / 2
        cy = y + height / 2
        c.circle(cx, cy, radius, stroke=1, fill=do_fill)

    elif shape_type == "line":
        # Line from (x, y) to (x + width, y + height).
        c.line(x, y, x + width, y + height)

    else:
        raise ValueError(
            f"Unknown shape_type {shape_type!r}. Choose from 'rect', 'circle', 'line'."
        )

    c.save()
    buf.seek(0)
    return _merge_overlay(reader, page_num, buf, dst)


def add_annotation(
    input_pdf: str | Path,
    page_num: int,
    x: float,
    y: float,
    content: str,
    output: str | Path | None,
    annotation_type: str = "text",
) -> Path:
    """Add an annotation to *page_num*.

    Parameters
    ----------
    annotation_type :
        ``"text"``  – renders visible text on the page (semi-transparent
        yellow background to mimic a sticky-note look).
        ``"highlight"`` – draws a translucent yellow rectangle spanning the
        area defined by (*x*, *y*, *x* + text-width, *y* + font-height).

    Returns
    -------
    Path to the written PDF.
    """
    src = ensure_pdf(input_pdf)
    dst = output_path(output, "edited.pdf")
    reader = PdfReader(str(src))

    page_w, page_h = _page_dimensions(reader, page_num)
    buf, c = _make_overlay(page_w, page_h)

    annotation_type = annotation_type.lower().strip()

    if annotation_type == "text":
        # Draw a pale-yellow note background, then the text on top.
        font_size = DEFAULT_FONT_SIZE
        c.setFont(DEFAULT_FONT, font_size)

        # Approximate text width for the background rectangle.
        text_width = c.stringWidth(content, DEFAULT_FONT, font_size)
        padding = 4
        bg_x = x - padding
        bg_y = y - padding
        bg_w = text_width + 2 * padding
        bg_h = font_size + 2 * padding

        c.setFillColor(Color(1, 1, 0.7, alpha=0.85))  # pale yellow
        c.rect(bg_x, bg_y, bg_w, bg_h, stroke=0, fill=1)

        c.setFillColor(Color(0, 0, 0))
        c.drawString(x, y, content)

    elif annotation_type == "highlight":
        # Translucent yellow rectangle – caller should set x, y and provide
        # content whose width determines the highlight span.
        font_size = DEFAULT_FONT_SIZE
        c.setFont(DEFAULT_FONT, font_size)
        text_width = c.stringWidth(content, DEFAULT_FONT, font_size)

        c.setFillColor(Color(1, 1, 0, alpha=0.35))
        c.rect(x, y, text_width, font_size, stroke=0, fill=1)

    else:
        raise ValueError(
            f"Unknown annotation_type {annotation_type!r}. "
            "Choose from 'text', 'highlight'."
        )

    c.save()
    buf.seek(0)
    return _merge_overlay(reader, page_num, buf, dst)
