"""PDF page cropping and resizing module.

Provides functions for cropping pages by setting PDF page boxes, resizing
pages via scaling, and trimming equal margins from all edges.  Analogous to
Adobe Acrobat's crop / resize tools.

All coordinate values are expressed in **points** (72 points = 1 inch).
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    FloatObject,
    NameObject,
    RectangleObject,
)

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf, output_path


# ---------------------------------------------------------------------------
# Valid PDF page-box names (PDF spec 14.11.2)
# ---------------------------------------------------------------------------

_VALID_BOX_TYPES = frozenset({
    "MediaBox",
    "CropBox",
    "BleedBox",
    "TrimBox",
    "ArtBox",
})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_pages(
    total: int,
    pages: Sequence[int] | None,
) -> list[int]:
    """Return a list of **0-based** page indices from a 1-indexed sequence.

    Parameters
    ----------
    total : int
        Total number of pages in the PDF.
    pages : sequence of int or None
        1-indexed page numbers supplied by the caller.  ``None`` means
        "all pages".

    Returns
    -------
    list[int]
        Validated 0-based indices.

    Raises
    ------
    InputError
        If any page number is out of range.
    """
    if pages is None:
        return list(range(total))

    indices: list[int] = []
    for p in pages:
        if not isinstance(p, int) or p < 1 or p > total:
            raise InputError(
                f"Page number {p} is out of range. "
                f"The PDF has {total} page(s) (1-indexed)."
            )
        indices.append(p - 1)
    return indices


def _write_pdf(writer: PdfWriter, dst: Path) -> Path:
    """Write the *writer* to *dst* and return the path."""
    with open(dst, "wb") as fh:
        writer.write(fh)
    return dst


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def crop_pages(
    input_pdf: str | Path,
    left: float,
    bottom: float,
    right: float,
    top: float,
    output: str | Path | None = None,
    pages: Sequence[int] | None = None,
) -> Path:
    """Crop pages by insetting each edge inward.

    The crop values are **offsets** measured from the corresponding edge of the
    current ``MediaBox`` toward the centre of the page.  For example,
    ``left=36`` removes half an inch from the left side.

    Parameters
    ----------
    input_pdf : str or Path
        Path to the source PDF file.
    left : float
        Points to trim from the left edge.
    bottom : float
        Points to trim from the bottom edge.
    right : float
        Points to trim from the right edge.
    top : float
        Points to trim from the top edge.
    output : str, Path, or None
        Destination path.  Defaults to ``cropped.pdf`` in the current
        working directory.
    pages : sequence of int or None
        1-indexed page numbers to crop.  ``None`` crops every page.

    Returns
    -------
    Path
        Path to the written PDF.

    Raises
    ------
    InputError
        If offsets are negative, exceed the page dimensions, or page
        numbers are out of range.
    """
    for name, val in (("left", left), ("bottom", bottom),
                      ("right", right), ("top", top)):
        if val < 0:
            raise InputError(f"Crop offset '{name}' must be non-negative, got {val}.")

    src = ensure_pdf(input_pdf)
    dst = output_path(output, "cropped.pdf")
    reader = PdfReader(str(src))
    writer = PdfWriter()

    target_indices = _resolve_pages(len(reader.pages), pages)

    for i, page in enumerate(reader.pages):
        if i in target_indices:
            mb = page.mediabox
            new_left = float(mb.left) + left
            new_bottom = float(mb.bottom) + bottom
            new_right = float(mb.right) - right
            new_top = float(mb.top) - top

            if new_left >= new_right:
                raise InputError(
                    f"Crop offsets (left={left}, right={right}) exceed the "
                    f"width of page {i + 1} "
                    f"({float(mb.right) - float(mb.left)} pt)."
                )
            if new_bottom >= new_top:
                raise InputError(
                    f"Crop offsets (bottom={bottom}, top={top}) exceed the "
                    f"height of page {i + 1} "
                    f"({float(mb.top) - float(mb.bottom)} pt)."
                )

            page.cropbox = RectangleObject([
                FloatObject(new_left),
                FloatObject(new_bottom),
                FloatObject(new_right),
                FloatObject(new_top),
            ])
        writer.add_page(page)

    return _write_pdf(writer, dst)


def resize_pages(
    input_pdf: str | Path,
    width: float,
    height: float,
    output: str | Path | None = None,
    pages: Sequence[int] | None = None,
) -> Path:
    """Resize pages to the specified dimensions using scaling.

    Each targeted page is scaled so that its ``MediaBox`` matches the
    requested *width* and *height*.  Content is scaled proportionally.

    Parameters
    ----------
    input_pdf : str or Path
        Path to the source PDF file.
    width : float
        Desired page width in points.
    height : float
        Desired page height in points.
    output : str, Path, or None
        Destination path.  Defaults to ``resized.pdf``.
    pages : sequence of int or None
        1-indexed page numbers to resize.  ``None`` resizes every page.

    Returns
    -------
    Path
        Path to the written PDF.

    Raises
    ------
    InputError
        If *width* or *height* is not positive, or page numbers are out
        of range.
    """
    if width <= 0:
        raise InputError(f"Width must be positive, got {width}.")
    if height <= 0:
        raise InputError(f"Height must be positive, got {height}.")

    src = ensure_pdf(input_pdf)
    dst = output_path(output, "resized.pdf")
    reader = PdfReader(str(src))
    writer = PdfWriter()

    target_indices = _resolve_pages(len(reader.pages), pages)

    for i, page in enumerate(reader.pages):
        if i in target_indices:
            mb = page.mediabox
            current_w = float(mb.width)
            current_h = float(mb.height)

            if current_w == 0 or current_h == 0:
                raise InputError(
                    f"Page {i + 1} has zero-width or zero-height MediaBox; "
                    "cannot scale."
                )

            sx = width / current_w
            sy = height / current_h
            page.scale(sx, sy)

        writer.add_page(page)

    return _write_pdf(writer, dst)


def trim_margins(
    input_pdf: str | Path,
    margin: float,
    output: str | Path | None = None,
    pages: Sequence[int] | None = None,
) -> Path:
    """Trim equal margins from all four sides of each page.

    This is a convenience wrapper around :func:`crop_pages` that applies the
    same inset to every edge.

    Parameters
    ----------
    input_pdf : str or Path
        Path to the source PDF file.
    margin : float
        Points to trim from each edge.
    output : str, Path, or None
        Destination path.  Defaults to ``trimmed.pdf``.
    pages : sequence of int or None
        1-indexed page numbers to trim.  ``None`` trims every page.

    Returns
    -------
    Path
        Path to the written PDF.

    Raises
    ------
    InputError
        If *margin* is negative or exceeds page dimensions.
    """
    if margin < 0:
        raise InputError(f"Margin must be non-negative, got {margin}.")

    return crop_pages(
        input_pdf,
        left=margin,
        bottom=margin,
        right=margin,
        top=margin,
        output=output if output is not None else "trimmed.pdf",
        pages=pages,
    )


def set_page_boxes(
    input_pdf: str | Path,
    box_type: str,
    left: float,
    bottom: float,
    right: float,
    top: float,
    output: str | Path | None = None,
    pages: Sequence[int] | None = None,
) -> Path:
    """Set a specific PDF page box to the given absolute coordinates.

    PDF defines five page-boundary boxes (see PDF Reference, section 14.11.2):

    * **MediaBox** -- physical medium size (required).
    * **CropBox** -- visible region when displayed/printed.
    * **BleedBox** -- extent of page content including bleed area.
    * **TrimBox** -- intended finished page size.
    * **ArtBox** -- meaningful content area.

    Parameters
    ----------
    input_pdf : str or Path
        Path to the source PDF file.
    box_type : str
        One of ``"MediaBox"``, ``"CropBox"``, ``"BleedBox"``,
        ``"TrimBox"``, or ``"ArtBox"`` (case-sensitive).
    left : float
        Left x-coordinate in points.
    bottom : float
        Bottom y-coordinate in points.
    right : float
        Right x-coordinate in points.
    top : float
        Top y-coordinate in points.
    output : str, Path, or None
        Destination path.  Defaults to ``boxed.pdf``.
    pages : sequence of int or None
        1-indexed page numbers to modify.  ``None`` modifies every page.

    Returns
    -------
    Path
        Path to the written PDF.

    Raises
    ------
    InputError
        If *box_type* is invalid, coordinates form a degenerate rectangle,
        or page numbers are out of range.
    """
    if box_type not in _VALID_BOX_TYPES:
        raise InputError(
            f"Invalid box_type {box_type!r}. "
            f"Must be one of: {', '.join(sorted(_VALID_BOX_TYPES))}."
        )

    if left >= right:
        raise InputError(
            f"Left ({left}) must be less than right ({right})."
        )
    if bottom >= top:
        raise InputError(
            f"Bottom ({bottom}) must be less than top ({top})."
        )

    src = ensure_pdf(input_pdf)
    dst = output_path(output, "boxed.pdf")
    reader = PdfReader(str(src))
    writer = PdfWriter()

    target_indices = _resolve_pages(len(reader.pages), pages)

    box_array = ArrayObject([
        FloatObject(left),
        FloatObject(bottom),
        FloatObject(right),
        FloatObject(top),
    ])

    for i, page in enumerate(reader.pages):
        if i in target_indices:
            page[NameObject(f"/{box_type}")] = box_array
        writer.add_page(page)

    return _write_pdf(writer, dst)
