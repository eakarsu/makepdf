"""PDF stamp features — predefined, custom text, and image stamps.

Provides functionality similar to Adobe Acrobat's stamp tool, allowing users
to place styled text stamps (e.g., "APPROVED", "DRAFT") or image stamps
(e.g., signatures, logos) at configurable positions on selected pages.
"""

import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf, output_path

# ---------------------------------------------------------------------------
# Predefined stamp definitions: label -> RGB colour tuple
# ---------------------------------------------------------------------------

STAMP_COLORS: dict[str, tuple[float, float, float]] = {
    "APPROVED": (0, 0.6, 0),
    "DRAFT": (0, 0, 0.8),
    "CONFIDENTIAL": (0.8, 0, 0),
    "FINAL": (0, 0.5, 0),
    "NOT APPROVED": (0.8, 0, 0),
    "VOID": (1, 0, 0),
    "FOR REVIEW": (0.8, 0.4, 0),
    "PRELIMINARY": (0, 0, 0.8),
    "EXPIRED": (0.5, 0.5, 0.5),
    "COPY": (0.4, 0.4, 0.4),
}

VALID_POSITIONS = {
    "center",
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
    "top-center",
    "bottom-center",
}

# Margin from page edge (in points) used for non-center positions.
_MARGIN = 36  # 0.5 inch


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_position(position: str) -> None:
    """Raise ``InputError`` if *position* is not a recognised placement."""
    if position not in VALID_POSITIONS:
        raise InputError(
            f"Invalid position '{position}'. "
            f"Must be one of {sorted(VALID_POSITIONS)}"
        )


def _resolve_pages(total: int, pages: list[int] | None) -> list[int]:
    """Return a list of 0-indexed page numbers from a 1-indexed user list.

    Parameters
    ----------
    total:
        Total number of pages in the document.
    pages:
        1-indexed page numbers supplied by the caller, or ``None`` for all.

    Returns
    -------
    list[int]
        0-indexed page numbers.

    Raises
    ------
    InputError
        If any page number is out of range.
    """
    if pages is None:
        return list(range(total))

    indices: list[int] = []
    for p in pages:
        if p < 1 or p > total:
            raise InputError(
                f"Page {p} is out of range (document has {total} pages)"
            )
        indices.append(p - 1)
    return indices


def _calc_position(
    position: str,
    page_width: float,
    page_height: float,
    stamp_width: float,
    stamp_height: float,
) -> tuple[float, float]:
    """Calculate the (x, y) origin for drawing the stamp.

    The returned coordinates refer to the bottom-left corner of the stamp
    bounding box.
    """
    cx = (page_width - stamp_width) / 2
    cy = (page_height - stamp_height) / 2

    positions: dict[str, tuple[float, float]] = {
        "center": (cx, cy),
        "top-left": (_MARGIN, page_height - stamp_height - _MARGIN),
        "top-right": (page_width - stamp_width - _MARGIN, page_height - stamp_height - _MARGIN),
        "bottom-left": (_MARGIN, _MARGIN),
        "bottom-right": (page_width - stamp_width - _MARGIN, _MARGIN),
        "top-center": (cx, page_height - stamp_height - _MARGIN),
        "bottom-center": (cx, _MARGIN),
    }
    return positions[position]


def _build_text_stamp_overlay(
    page_width: float,
    page_height: float,
    text: str,
    position: str,
    font_size: float,
    color: tuple[float, float, float],
    border: bool,
    opacity: float,
    angle: float,
) -> io.BytesIO:
    """Create an in-memory single-page PDF with a styled text stamp.

    The stamp consists of the supplied *text* rendered in Helvetica-Bold with
    an optional rectangular border, placed at the requested *position*.

    Returns
    -------
    io.BytesIO
        A seeked-to-zero buffer containing a one-page PDF overlay.
    """
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=(page_width, page_height))

    # Measure text to determine stamp dimensions.
    font_name = "Helvetica-Bold"
    c.setFont(font_name, font_size)
    text_width = c.stringWidth(text, font_name, font_size)

    padding_x = font_size * 0.5
    padding_y = font_size * 0.35
    stamp_width = text_width + 2 * padding_x
    stamp_height = font_size + 2 * padding_y

    x, y = _calc_position(position, page_width, page_height, stamp_width, stamp_height)

    c.saveState()

    # If the stamp should be rotated we rotate around its centre.
    if angle != 0:
        center_x = x + stamp_width / 2
        center_y = y + stamp_height / 2
        c.translate(center_x, center_y)
        c.rotate(angle)
        c.translate(-stamp_width / 2, -stamp_height / 2)
        # After the transforms, drawing origin is relative to stamp bbox.
        draw_x = 0.0
        draw_y = 0.0
    else:
        draw_x = x
        draw_y = y

    # Semi-transparent filled background rectangle.
    bg_color = Color(color[0], color[1], color[2], alpha=opacity * 0.15)
    c.setFillColor(bg_color)
    c.setStrokeColor(Color(color[0], color[1], color[2], alpha=opacity))
    c.setLineWidth(2)

    if border:
        c.roundRect(draw_x, draw_y, stamp_width, stamp_height, radius=4, fill=1, stroke=1)
    else:
        c.roundRect(draw_x, draw_y, stamp_width, stamp_height, radius=4, fill=1, stroke=0)

    # Draw the text.
    c.setFillColor(Color(color[0], color[1], color[2], alpha=opacity))
    c.setFont(font_name, font_size)
    text_x = draw_x + padding_x
    text_y = draw_y + padding_y
    c.drawString(text_x, text_y, text)

    c.restoreState()
    c.save()
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def add_stamp(
    input_pdf: str | Path,
    stamp_type: str,
    output: str | Path | None = None,
    pages: list[int] | None = None,
    position: str = "center",
    opacity: float = 0.5,
    angle: float = 0,
) -> Path:
    """Add a predefined stamp to one or more pages of a PDF.

    Parameters
    ----------
    input_pdf:
        Path to the source PDF file.
    stamp_type:
        One of the predefined stamp labels: ``"APPROVED"``, ``"DRAFT"``,
        ``"CONFIDENTIAL"``, ``"FINAL"``, ``"NOT APPROVED"``, ``"VOID"``,
        ``"FOR REVIEW"``, ``"PRELIMINARY"``, ``"EXPIRED"``, ``"COPY"``.
    output:
        Destination path for the stamped PDF.  When ``None`` the file is
        written alongside the input with a ``_stamped`` suffix.
    pages:
        1-indexed list of pages to stamp.  ``None`` stamps every page.
    position:
        Placement of the stamp on the page.  One of ``"center"``,
        ``"top-left"``, ``"top-right"``, ``"bottom-left"``,
        ``"bottom-right"``, ``"top-center"``, ``"bottom-center"``.
    opacity:
        Stamp opacity from 0.0 (invisible) to 1.0 (fully opaque).
    angle:
        Counter-clockwise rotation in degrees.

    Returns
    -------
    Path
        The path to the output PDF.

    Raises
    ------
    InputError
        If the stamp type, position, or page numbers are invalid.
    """
    stamp_type_upper = stamp_type.upper()
    if stamp_type_upper not in STAMP_COLORS:
        raise InputError(
            f"Unknown stamp type '{stamp_type}'. "
            f"Must be one of {sorted(STAMP_COLORS.keys())}"
        )
    _validate_position(position)

    color = STAMP_COLORS[stamp_type_upper]
    pdf_path = ensure_pdf(input_pdf)
    out = output_path(output, pdf_path.stem + "_stamped.pdf")
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()

    target_pages = _resolve_pages(len(reader.pages), pages)

    for idx, page in enumerate(reader.pages):
        if idx in target_pages:
            page_width = float(page.mediabox.width)
            page_height = float(page.mediabox.height)

            overlay_buf = _build_text_stamp_overlay(
                page_width=page_width,
                page_height=page_height,
                text=stamp_type_upper,
                position=position,
                font_size=36,
                color=color,
                border=True,
                opacity=opacity,
                angle=angle,
            )
            overlay_page = PdfReader(overlay_buf).pages[0]
            page.merge_page(overlay_page)

        writer.add_page(page)

    with open(out, "wb") as f:
        writer.write(f)

    return out


def add_custom_stamp(
    input_pdf: str | Path,
    text: str,
    output: str | Path | None = None,
    pages: list[int] | None = None,
    position: str = "center",
    font_size: float = 36,
    color: tuple[float, float, float] = (1, 0, 0),
    border: bool = True,
    opacity: float = 0.5,
    angle: float = 0,
) -> Path:
    """Add a custom text stamp to one or more pages of a PDF.

    This function is similar to :func:`add_stamp` but allows full control
    over the stamp text, colour, font size, and whether a border is drawn.

    Parameters
    ----------
    input_pdf:
        Path to the source PDF file.
    text:
        The text to display inside the stamp.
    output:
        Destination path for the stamped PDF.  When ``None`` the file is
        written alongside the input with a ``_stamped`` suffix.
    pages:
        1-indexed list of pages to stamp.  ``None`` stamps every page.
    position:
        Placement of the stamp on the page.  One of ``"center"``,
        ``"top-left"``, ``"top-right"``, ``"bottom-left"``,
        ``"bottom-right"``, ``"top-center"``, ``"bottom-center"``.
    font_size:
        Font size in points for the stamp text.
    color:
        RGB colour tuple with components in the range 0.0–1.0.
    border:
        Whether to draw a rectangular border around the stamp.
    opacity:
        Stamp opacity from 0.0 (invisible) to 1.0 (fully opaque).
    angle:
        Counter-clockwise rotation in degrees.

    Returns
    -------
    Path
        The path to the output PDF.

    Raises
    ------
    InputError
        If the position or page numbers are invalid, or if *text* is empty.
    """
    if not text or not text.strip():
        raise InputError("Stamp text must not be empty")
    _validate_position(position)

    pdf_path = ensure_pdf(input_pdf)
    out = output_path(output, pdf_path.stem + "_stamped.pdf")
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()

    target_pages = _resolve_pages(len(reader.pages), pages)

    for idx, page in enumerate(reader.pages):
        if idx in target_pages:
            page_width = float(page.mediabox.width)
            page_height = float(page.mediabox.height)

            overlay_buf = _build_text_stamp_overlay(
                page_width=page_width,
                page_height=page_height,
                text=text,
                position=position,
                font_size=font_size,
                color=color,
                border=border,
                opacity=opacity,
                angle=angle,
            )
            overlay_page = PdfReader(overlay_buf).pages[0]
            page.merge_page(overlay_page)

        writer.add_page(page)

    with open(out, "wb") as f:
        writer.write(f)

    return out


def add_image_stamp(
    input_pdf: str | Path,
    image_path: str | Path,
    output: str | Path | None = None,
    pages: list[int] | None = None,
    position: str = "bottom-right",
    scale: float = 0.3,
    opacity: float = 0.8,
) -> Path:
    """Add an image stamp (e.g., a signature or company logo) to pages.

    The image is scaled relative to the page width while preserving its
    aspect ratio, then placed at the requested *position*.

    Parameters
    ----------
    input_pdf:
        Path to the source PDF file.
    image_path:
        Path to the image file (PNG, JPEG, etc.) to use as the stamp.
    output:
        Destination path for the stamped PDF.  When ``None`` the file is
        written alongside the input with a ``_stamped`` suffix.
    pages:
        1-indexed list of pages to stamp.  ``None`` stamps every page.
    position:
        Placement of the stamp on the page.  One of ``"center"``,
        ``"top-left"``, ``"top-right"``, ``"bottom-left"``,
        ``"bottom-right"``, ``"top-center"``, ``"bottom-center"``.
    scale:
        Scale factor relative to the page width (0.0–1.0).
    opacity:
        Stamp opacity from 0.0 (invisible) to 1.0 (fully opaque).

    Returns
    -------
    Path
        The path to the output PDF.

    Raises
    ------
    InputError
        If the image file does not exist, or if the position or page numbers
        are invalid.
    """
    _validate_position(position)

    pdf_path = ensure_pdf(input_pdf)
    img_path = Path(image_path)
    if not img_path.exists():
        raise InputError(f"Image file not found: {img_path}")

    out = output_path(output, pdf_path.stem + "_stamped.pdf")
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()

    # Read image dimensions once.
    rl_img = ImageReader(str(img_path))
    img_orig_w, img_orig_h = rl_img.getSize()

    target_pages = _resolve_pages(len(reader.pages), pages)

    for idx, page in enumerate(reader.pages):
        if idx in target_pages:
            page_width = float(page.mediabox.width)
            page_height = float(page.mediabox.height)

            # Scale image relative to page width, preserving aspect ratio.
            img_w = page_width * scale
            img_h = img_w * (img_orig_h / img_orig_w)

            # Clamp if the scaled height exceeds the proportional limit.
            if img_h > page_height * scale:
                img_h = page_height * scale
                img_w = img_h * (img_orig_w / img_orig_h)

            x, y = _calc_position(position, page_width, page_height, img_w, img_h)

            buf = io.BytesIO()
            c = Canvas(buf, pagesize=(page_width, page_height))
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
