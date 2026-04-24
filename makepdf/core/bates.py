"""Bates numbering for PDF files.

Provides sequential stamping of unique identifiers on every page of one or
more PDF documents — the standard approach used in legal discovery, regulatory
filings, and large-scale document management (comparable to Adobe Acrobat's
Bates numbering feature).

Each stamp has the format ``{prefix}{number}{suffix}`` where *number* is
zero-padded to the requested width.
"""

import io
from pathlib import Path
from typing import Sequence

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color
from reportlab.pdfgen.canvas import Canvas

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf, output_path

# Positions recognised by the stamping functions.
_VALID_POSITIONS = frozenset({
    "bottom-left",
    "bottom-center",
    "bottom-right",
    "top-left",
    "top-center",
    "top-right",
})

# Default margin from the page edge (in points — 36 pt ≈ 0.5 in).
_MARGIN = 36


def _format_bates(number: int, prefix: str, suffix: str, digits: int) -> str:
    """Return the formatted Bates label for *number*.

    Parameters
    ----------
    number : int
        The current sequential number.
    prefix : str
        Text prepended before the numeric portion.
    suffix : str
        Text appended after the numeric portion.
    digits : int
        Minimum width of the zero-padded numeric portion.

    Returns
    -------
    str
        The complete Bates label, e.g. ``"ABC000001XYZ"``.
    """
    return f"{prefix}{number:0{digits}d}{suffix}"


def _compute_position(
    position: str,
    page_width: float,
    page_height: float,
    text_width: float,
    font_size: float,
) -> tuple[float, float]:
    """Return ``(x, y)`` coordinates for the Bates label.

    The label is placed with a margin of :data:`_MARGIN` points from the
    relevant page edges.  Vertical placement uses the font descender
    approximation so that baseline positioning looks natural.

    Parameters
    ----------
    position : str
        One of the values in :data:`_VALID_POSITIONS`.
    page_width : float
        Width of the current page in points.
    page_height : float
        Height of the current page in points.
    text_width : float
        Width of the rendered text string in points (as measured by
        ``Canvas.stringWidth``).
    font_size : float
        Font size in points, used to offset vertical placement.

    Returns
    -------
    tuple[float, float]
        ``(x, y)`` suitable for ``Canvas.drawString``.
    """
    # Horizontal placement
    if position.endswith("-left"):
        x = _MARGIN
    elif position.endswith("-right"):
        x = page_width - _MARGIN - text_width
    else:  # center
        x = (page_width - text_width) / 2

    # Vertical placement
    if position.startswith("bottom"):
        y = _MARGIN
    else:  # top
        y = page_height - _MARGIN - font_size

    return x, y


def _create_bates_overlay(
    label: str,
    page_width: float,
    page_height: float,
    position: str,
    font: str,
    font_size: float,
    color: tuple[float, float, float],
) -> io.BytesIO:
    """Build a single-page PDF overlay containing the Bates label.

    Parameters
    ----------
    label : str
        The formatted Bates string to render.
    page_width : float
        Target page width in points.
    page_height : float
        Target page height in points.
    position : str
        Placement identifier (see :data:`_VALID_POSITIONS`).
    font : str
        PostScript font name recognised by reportlab (e.g. ``"Helvetica"``).
    font_size : float
        Size in points.
    color : tuple[float, float, float]
        RGB colour components, each in the range 0.0–1.0.

    Returns
    -------
    io.BytesIO
        A seeked-to-zero buffer containing a valid single-page PDF.
    """
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=(page_width, page_height))
    c.saveState()

    c.setFont(font, font_size)
    c.setFillColor(Color(*color))

    text_width = c.stringWidth(label, font, font_size)
    x, y = _compute_position(position, page_width, page_height, text_width, font_size)
    c.drawString(x, y, label)

    c.restoreState()
    c.save()
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def add_bates_numbers(
    input_pdf: str | Path,
    output: str | Path | None = None,
    prefix: str = "",
    suffix: str = "",
    start: int = 1,
    digits: int = 6,
    position: str = "bottom-center",
    font: str = "Helvetica",
    font_size: float = 10,
    color: tuple[float, float, float] = (0, 0, 0),
) -> Path:
    """Add Bates numbers to every page of a single PDF.

    Each page receives a unique sequential label in the format
    ``{prefix}{number:0<digits>d}{suffix}``.  The overlay is merged onto the
    existing page content so that the original layout is preserved.

    Parameters
    ----------
    input_pdf : str | Path
        Path to the source PDF file.
    output : str | Path | None, optional
        Destination path for the stamped PDF.  When *None* the output is
        written to ``<stem>_bates.pdf`` in the current working directory.
    prefix : str, optional
        Text placed before the numeric portion of the label.
    suffix : str, optional
        Text placed after the numeric portion of the label.
    start : int, optional
        First Bates number (default ``1``).
    digits : int, optional
        Minimum zero-padded width of the numeric portion (default ``6``).
    position : str, optional
        Where to place the label on each page.  Must be one of
        ``"bottom-left"``, ``"bottom-center"``, ``"bottom-right"``,
        ``"top-left"``, ``"top-center"``, or ``"top-right"``.
        Defaults to ``"bottom-center"``.
    font : str, optional
        PostScript font name (default ``"Helvetica"``).
    font_size : float, optional
        Font size in points (default ``10``).
    color : tuple[float, float, float], optional
        RGB colour, each component in 0.0–1.0 (default black).

    Returns
    -------
    Path
        The path to the generated output PDF.

    Raises
    ------
    InputError
        If *input_pdf* does not exist, is not a PDF, or *position* is
        invalid.
    """
    if position not in _VALID_POSITIONS:
        raise InputError(
            f"Invalid position '{position}'. "
            f"Must be one of {sorted(_VALID_POSITIONS)}"
        )

    pdf_path = ensure_pdf(input_pdf)
    out = output_path(output, pdf_path.stem + "_bates.pdf")

    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()

    current_number = start

    for page in reader.pages:
        page_box = page.mediabox
        page_width = float(page_box.width)
        page_height = float(page_box.height)

        label = _format_bates(current_number, prefix, suffix, digits)
        overlay_buf = _create_bates_overlay(
            label, page_width, page_height, position, font, font_size, color,
        )

        overlay_page = PdfReader(overlay_buf).pages[0]
        page.merge_page(overlay_page)
        writer.add_page(page)

        current_number += 1

    with open(out, "wb") as f:
        writer.write(f)

    return out


def add_bates_to_batch(
    pdf_paths: Sequence[str | Path],
    output_dir: str | Path | None = None,
    prefix: str = "",
    suffix: str = "",
    start: int = 1,
    digits: int = 6,
    position: str = "bottom-center",
    font: str = "Helvetica",
    font_size: float = 10,
    color: tuple[float, float, float] = (0, 0, 0),
) -> list[Path]:
    """Add continuous Bates numbers across multiple PDF files.

    The numbering is **sequential across all files**: the first page of the
    second file continues where the last page of the first file left off.

    Parameters
    ----------
    pdf_paths : Sequence[str | Path]
        Ordered list of PDF file paths to stamp.
    output_dir : str | Path | None, optional
        Directory for the stamped files.  Each output file is named
        ``<original_stem>_bates.pdf``.  When *None* the files are written
        alongside the originals.
    prefix : str, optional
        Text placed before the numeric portion of the label.
    suffix : str, optional
        Text placed after the numeric portion of the label.
    start : int, optional
        First Bates number (default ``1``).
    digits : int, optional
        Minimum zero-padded width of the numeric portion (default ``6``).
    position : str, optional
        Label placement (see :func:`add_bates_numbers` for allowed values).
        Defaults to ``"bottom-center"``.
    font : str, optional
        PostScript font name (default ``"Helvetica"``).
    font_size : float, optional
        Font size in points (default ``10``).
    color : tuple[float, float, float], optional
        RGB colour, each component in 0.0–1.0 (default black).

    Returns
    -------
    list[Path]
        Paths to all generated output PDFs, in the same order as
        *pdf_paths*.

    Raises
    ------
    InputError
        If any path does not exist or is not a PDF, if *position* is
        invalid, or if *pdf_paths* is empty.
    """
    if not pdf_paths:
        raise InputError("pdf_paths must not be empty.")

    if position not in _VALID_POSITIONS:
        raise InputError(
            f"Invalid position '{position}'. "
            f"Must be one of {sorted(_VALID_POSITIONS)}"
        )

    resolved_dir: Path | None = None
    if output_dir is not None:
        resolved_dir = Path(output_dir)
        resolved_dir.mkdir(parents=True, exist_ok=True)

    output_paths: list[Path] = []
    current_number = start

    for pdf_input in pdf_paths:
        pdf_path = ensure_pdf(pdf_input)

        if resolved_dir is not None:
            out = resolved_dir / (pdf_path.stem + "_bates.pdf")
        else:
            out = pdf_path.parent / (pdf_path.stem + "_bates.pdf")

        reader = PdfReader(str(pdf_path))
        writer = PdfWriter()

        for page in reader.pages:
            page_box = page.mediabox
            page_width = float(page_box.width)
            page_height = float(page_box.height)

            label = _format_bates(current_number, prefix, suffix, digits)
            overlay_buf = _create_bates_overlay(
                label, page_width, page_height, position, font, font_size, color,
            )

            overlay_page = PdfReader(overlay_buf).pages[0]
            page.merge_page(overlay_page)
            writer.add_page(page)

            current_number += 1

        with open(out, "wb") as f:
            writer.write(f)

        output_paths.append(out)

    return output_paths
