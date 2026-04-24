"""PDF redaction features — black-out areas, search-and-redact text.

Provides tools similar to Adobe Acrobat's redaction workflow: mark regions
or text for redaction, then apply opaque rectangles that permanently obscure
the content.  Overlays are merged via *pypdf* so the black boxes become part
of the page content stream.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Sequence

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen.canvas import Canvas

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf, output_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_rect_overlay(
    page_width: float,
    page_height: float,
    rects: list[tuple[float, float, float, float]],
    fill_color: tuple[float, float, float],
) -> io.BytesIO:
    """Return an in-memory single-page PDF with filled rectangles.

    Each rect is ``(x, y, width, height)`` in PDF points with the origin at
    the bottom-left corner of the page.
    """
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=(page_width, page_height))
    c.setFillColorRGB(*fill_color)
    c.setStrokeColorRGB(*fill_color)
    for x, y, w, h in rects:
        c.rect(x, y, w, h, stroke=0, fill=1)
    c.save()
    buf.seek(0)
    return buf


def _page_dimensions(page) -> tuple[float, float]:
    """Extract width and height from a pypdf page object."""
    box = page.mediabox
    return float(box.width), float(box.height)


def _validate_fill_color(fill_color: tuple) -> None:
    """Ensure *fill_color* is a 3-tuple of floats in [0, 1]."""
    if (
        not isinstance(fill_color, (tuple, list))
        or len(fill_color) != 3
        or not all(isinstance(v, (int, float)) for v in fill_color)
    ):
        raise InputError(
            "fill_color must be a 3-tuple of numeric values, "
            f"e.g. (0, 0, 0). Got: {fill_color!r}"
        )
    if not all(0 <= v <= 1 for v in fill_color):
        raise InputError(
            "fill_color values must be between 0 and 1. "
            f"Got: {fill_color!r}"
        )


def _find_text_positions_on_page(page, search_term: str) -> list[tuple[float, float, float, float]]:
    """Return approximate bounding rectangles for *search_term* on *page*.

    Uses the page's ``extract_text`` with layout preservation to find
    occurrences, then estimates positions based on character-level visitor
    data when available, falling back to a heuristic full-page scan.

    Each returned tuple is ``(x, y, width, height)`` in PDF user-space
    coordinates (origin at bottom-left).
    """
    rects: list[tuple[float, float, float, float]] = []
    page_width, page_height = _page_dimensions(page)

    # Attempt character-level extraction via visitor
    parts: list[dict] = []

    def visitor_body(text, cm, tm, font_dict, font_size):  # noqa: ARG001
        """Collect text fragments with their transformation matrices."""
        if text and text.strip():
            # tm is the text matrix: [a, b, c, d, e, f]
            # (e, f) gives the position in user space.
            x_pos = tm[4]
            y_pos = tm[5]
            parts.append({
                "text": text,
                "x": float(x_pos),
                "y": float(y_pos),
                "font_size": float(font_size) if font_size else 12.0,
            })

    try:
        page.extract_text(visitor_text=visitor_body)
    except Exception:
        # Visitor extraction is best-effort; fall back below.
        parts = []

    if parts:
        # Walk through collected fragments, concatenate contiguous text, and
        # locate the search term.
        for part in parts:
            text = part["text"]
            idx = 0
            while True:
                pos = text.lower().find(search_term.lower(), idx)
                if pos == -1:
                    break
                fs = part["font_size"]
                # Approximate: each character is ~0.6 * font_size wide
                char_width = fs * 0.6
                x = part["x"] + pos * char_width
                y = part["y"] - fs * 0.2  # slight downward offset
                w = len(search_term) * char_width
                h = fs * 1.4  # generous height to cover ascenders/descenders
                rects.append((x, y, w, h))
                idx = pos + 1

    if not rects:
        # Fallback: use plain extract_text to confirm the term is on the
        # page, then do a simple heuristic overlay based on content stream
        # analysis.
        full_text = page.extract_text() or ""
        if search_term.lower() in full_text.lower():
            # Without precise glyph positions we create a conservative
            # set of rectangles.  Split text into lines and estimate
            # vertical position for each matching line.
            lines = full_text.split("\n")
            # Assume standard 12pt font, ~50 lines per page as baseline
            estimated_line_height = page_height / max(len(lines), 1)
            char_width_est = 7.0  # rough average for 12pt

            for line_idx, line in enumerate(lines):
                col = 0
                lower_line = line.lower()
                lower_term = search_term.lower()
                while True:
                    pos = lower_line.find(lower_term, col)
                    if pos == -1:
                        break
                    x = 36 + pos * char_width_est  # 36pt ≈ 0.5 inch margin
                    # PDF y-axis goes bottom-to-top; first line is near top
                    y = page_height - (line_idx + 1) * estimated_line_height
                    w = len(search_term) * char_width_est * 1.1
                    h = estimated_line_height * 1.2
                    rects.append((x, y, w, h))
                    col = pos + 1

    return rects


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def redact_area(
    input_pdf: str | Path,
    page_num: int,
    x: float,
    y: float,
    width: float,
    height: float,
    output: str | Path | None = None,
    fill_color: tuple[float, float, float] = (0, 0, 0),
) -> Path:
    """Black out a rectangular area on a specific page.

    Draws an opaque filled rectangle over the specified region and merges it
    into the page content stream so the underlying content is visually
    obscured.

    Parameters
    ----------
    input_pdf : str or Path
        Path to the source PDF file.
    page_num : int
        Zero-indexed page number to redact.
    x : float
        Horizontal offset (points) from the left edge of the page.
    y : float
        Vertical offset (points) from the bottom edge of the page.
    width : float
        Width of the redaction rectangle in points.
    height : float
        Height of the redaction rectangle in points.
    output : str, Path, or None
        Destination path.  Defaults to ``<stem>_redacted.pdf``.
    fill_color : tuple of float
        RGB fill colour with each channel in ``[0, 1]``.  Defaults to black.

    Returns
    -------
    Path
        The path to the redacted PDF.

    Raises
    ------
    InputError
        If the file is not a valid PDF, the page number is out of range, or
        the rectangle dimensions are invalid.
    """
    pdf_path = ensure_pdf(input_pdf)
    _validate_fill_color(fill_color)

    reader = PdfReader(str(pdf_path))
    num_pages = len(reader.pages)

    if not isinstance(page_num, int) or page_num < 0 or page_num >= num_pages:
        raise InputError(
            f"page_num must be between 0 and {num_pages - 1} "
            f"(PDF has {num_pages} page(s)). Got: {page_num}"
        )

    if width <= 0 or height <= 0:
        raise InputError(
            f"width and height must be positive. Got width={width}, height={height}"
        )

    out = output_path(output, pdf_path.stem + "_redacted.pdf")
    writer = PdfWriter()

    for idx, page in enumerate(reader.pages):
        if idx == page_num:
            pw, ph = _page_dimensions(page)
            overlay_buf = _build_rect_overlay(pw, ph, [(x, y, width, height)], fill_color)
            overlay_page = PdfReader(overlay_buf).pages[0]
            page.merge_page(overlay_page)
        writer.add_page(page)

    with open(out, "wb") as f:
        writer.write(f)

    return out


def redact_text(
    input_pdf: str | Path,
    search_term: str,
    output: str | Path | None = None,
    fill_color: tuple[float, float, float] = (0, 0, 0),
    pages: list[int] | None = None,
) -> Path:
    """Find all occurrences of *search_term* and cover them with opaque boxes.

    Text positions are estimated via pypdf's text-extraction visitor API and
    a heuristic fallback.  The redaction rectangles are merged into each
    page's content stream.

    Parameters
    ----------
    input_pdf : str or Path
        Path to the source PDF file.
    search_term : str
        Plain text to locate and redact (case-insensitive).
    output : str, Path, or None
        Destination path.  Defaults to ``<stem>_redacted.pdf``.
    fill_color : tuple of float
        RGB fill colour with each channel in ``[0, 1]``.  Defaults to black.
    pages : list of int or None
        Optional **1-indexed** page numbers to restrict the search to.
        ``None`` means all pages.

    Returns
    -------
    Path
        The path to the redacted PDF.

    Raises
    ------
    InputError
        If the file is not a valid PDF, the search term is empty, or any
        page number in *pages* is out of range.
    """
    pdf_path = ensure_pdf(input_pdf)
    _validate_fill_color(fill_color)

    if not search_term:
        raise InputError("search_term must not be empty.")

    reader = PdfReader(str(pdf_path))
    num_pages = len(reader.pages)

    # Validate page list (1-indexed)
    if pages is not None:
        for p in pages:
            if not isinstance(p, int) or p < 1 or p > num_pages:
                raise InputError(
                    f"Page numbers must be between 1 and {num_pages}. Got: {p}"
                )
        target_indices = {p - 1 for p in pages}
    else:
        target_indices = set(range(num_pages))

    out = output_path(output, pdf_path.stem + "_redacted.pdf")
    writer = PdfWriter()
    redaction_count = 0

    for idx, page in enumerate(reader.pages):
        if idx in target_indices:
            rects = _find_text_positions_on_page(page, search_term)
            if rects:
                pw, ph = _page_dimensions(page)
                overlay_buf = _build_rect_overlay(pw, ph, rects, fill_color)
                overlay_page = PdfReader(overlay_buf).pages[0]
                page.merge_page(overlay_page)
                redaction_count += len(rects)
        writer.add_page(page)

    if redaction_count == 0:
        raise InputError(
            f"Search term '{search_term}' was not found in the specified pages."
        )

    with open(out, "wb") as f:
        writer.write(f)

    return out


def search_and_redact(
    input_pdf: str | Path,
    patterns: Sequence[str],
    output: str | Path | None = None,
    fill_color: tuple[float, float, float] = (0, 0, 0),
) -> Path:
    """Redact all regex-pattern matches across the entire PDF.

    Useful for bulk removal of sensitive data such as Social Security numbers,
    e-mail addresses, phone numbers, and similar structured text.

    Parameters
    ----------
    input_pdf : str or Path
        Path to the source PDF file.
    patterns : sequence of str
        Regular expression patterns (as strings).  Each pattern is compiled
        and matched against the extracted text of every page.
    output : str, Path, or None
        Destination path.  Defaults to ``<stem>_redacted.pdf``.
    fill_color : tuple of float
        RGB fill colour with each channel in ``[0, 1]``.  Defaults to black.

    Returns
    -------
    Path
        The path to the redacted PDF.

    Raises
    ------
    InputError
        If the file is not a valid PDF, *patterns* is empty, or a pattern
        has invalid regex syntax.
    """
    pdf_path = ensure_pdf(input_pdf)
    _validate_fill_color(fill_color)

    if not patterns:
        raise InputError("patterns must contain at least one regex pattern.")

    # Pre-compile patterns so syntax errors surface early.
    compiled: list[re.Pattern] = []
    for pat in patterns:
        try:
            compiled.append(re.compile(pat))
        except re.error as exc:
            raise InputError(f"Invalid regex pattern '{pat}': {exc}") from exc

    reader = PdfReader(str(pdf_path))
    out = output_path(output, pdf_path.stem + "_redacted.pdf")
    writer = PdfWriter()
    total_redactions = 0

    for page in reader.pages:
        all_rects: list[tuple[float, float, float, float]] = []

        # Collect all unique match strings on this page.
        full_text = page.extract_text() or ""
        matched_terms: set[str] = set()
        for regex in compiled:
            for m in regex.finditer(full_text):
                matched_terms.add(m.group())

        # For each unique matched string, find approximate positions.
        for term in matched_terms:
            rects = _find_text_positions_on_page(page, term)
            all_rects.extend(rects)

        if all_rects:
            pw, ph = _page_dimensions(page)
            overlay_buf = _build_rect_overlay(pw, ph, all_rects, fill_color)
            overlay_page = PdfReader(overlay_buf).pages[0]
            page.merge_page(overlay_page)
            total_redactions += len(all_rects)

        writer.add_page(page)

    if total_redactions == 0:
        raise InputError(
            "No matches found for the supplied patterns in the PDF."
        )

    with open(out, "wb") as f:
        writer.write(f)

    return out
