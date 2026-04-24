"""Compare two PDF documents by text, metadata, and structure.

Provides functionality similar to Adobe Acrobat's Compare Documents feature,
allowing users to identify differences between two PDF files at multiple levels:
text content, metadata fields, and structural properties (page size, rotation).
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf, output_path


# ---------------------------------------------------------------------------
# Colours used in the diff report
# ---------------------------------------------------------------------------
_COLOR_ADDED = Color(0.15, 0.65, 0.15, 1)    # green
_COLOR_REMOVED = Color(0.80, 0.15, 0.15, 1)  # red
_COLOR_HEADING = Color(0.10, 0.10, 0.55, 1)  # dark blue
_COLOR_NORMAL = Color(0, 0, 0, 1)             # black

_FONT_NAME = "Helvetica"
_FONT_NAME_BOLD = "Helvetica-Bold"
_FONT_SIZE = 9
_HEADING_SIZE = 12
_LINE_HEIGHT = 12
_MARGIN = 50


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_pages_text(reader: PdfReader) -> list[str]:
    """Return a list of extracted text strings, one per page."""
    return [page.extract_text() or "" for page in reader.pages]


def _metadata_dict(reader: PdfReader) -> dict[str, str]:
    """Return PDF metadata as a plain ``{field: value}`` dict.

    Normalises keys by stripping the leading ``/`` that pypdf may include,
    and converts all values to strings so they are safely comparable.
    """
    meta = reader.metadata
    if meta is None:
        return {}
    result: dict[str, str] = {}
    for key in meta:
        clean_key = str(key).lstrip("/")
        value = meta[key]
        result[clean_key] = str(value) if value is not None else ""
    return result


def _page_properties(page: Any) -> dict[str, Any]:
    """Extract comparable structural properties from a single PDF page."""
    mediabox = page.mediabox
    width = float(mediabox.width)
    height = float(mediabox.height)
    rotation = int(page.get("/Rotate", 0))
    return {
        "width": round(width, 2),
        "height": round(height, 2),
        "rotation": rotation,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compare_text(
    pdf_a: str | Path,
    pdf_b: str | Path,
) -> dict[str, Any]:
    """Compare two PDFs by their extracted text content, page by page.

    For each page present in either document the function runs a unified diff.
    Pages that exist in only one of the two documents are reported as wholly
    added or removed.

    Args:
        pdf_a: Path to the first PDF file.
        pdf_b: Path to the second PDF file.

    Returns:
        A dict with the following keys:

        - **identical** (*bool*) -- ``True`` when the text of every page
          matches exactly.
        - **pages_a** (*int*) -- Total page count of *pdf_a*.
        - **pages_b** (*int*) -- Total page count of *pdf_b*.
        - **differences** (*list[dict]*) -- One entry per page that differs.
          Each entry contains:

          - ``page`` (*int*) -- 1-indexed page number.
          - ``type`` (*str*) -- One of ``"added"``, ``"removed"``, or
            ``"changed"``.
          - ``content`` (*str*) -- Human-readable description of the
            difference (unified-diff excerpt for changed pages, or a note
            that the page was added / removed).

    Raises:
        InputError: If either path does not point to a valid PDF file.
    """
    path_a = ensure_pdf(pdf_a)
    path_b = ensure_pdf(pdf_b)

    reader_a = PdfReader(path_a)
    reader_b = PdfReader(path_b)

    text_a = _read_pages_text(reader_a)
    text_b = _read_pages_text(reader_b)

    pages_a = len(text_a)
    pages_b = len(text_b)
    max_pages = max(pages_a, pages_b)

    differences: list[dict[str, Any]] = []

    for i in range(max_pages):
        page_num = i + 1
        has_a = i < pages_a
        has_b = i < pages_b

        if has_a and not has_b:
            differences.append({
                "page": page_num,
                "type": "removed",
                "content": f"Page {page_num} exists only in the first PDF.",
            })
        elif has_b and not has_a:
            differences.append({
                "page": page_num,
                "type": "added",
                "content": f"Page {page_num} exists only in the second PDF.",
            })
        else:
            lines_a = text_a[i].splitlines(keepends=True)
            lines_b = text_b[i].splitlines(keepends=True)
            diff = list(difflib.unified_diff(
                lines_a,
                lines_b,
                fromfile=f"pdf_a page {page_num}",
                tofile=f"pdf_b page {page_num}",
                lineterm="",
            ))
            if diff:
                differences.append({
                    "page": page_num,
                    "type": "changed",
                    "content": "\n".join(diff),
                })

    return {
        "identical": len(differences) == 0,
        "pages_a": pages_a,
        "pages_b": pages_b,
        "differences": differences,
    }


def compare_metadata(
    pdf_a: str | Path,
    pdf_b: str | Path,
) -> dict[str, Any]:
    """Compare the metadata fields of two PDF files.

    Checks every metadata key present in either document and reports fields
    whose values differ or that are missing from one side.

    Args:
        pdf_a: Path to the first PDF file.
        pdf_b: Path to the second PDF file.

    Returns:
        A dict with:

        - **identical** (*bool*) -- ``True`` when all metadata fields match.
        - **differences** (*list[dict]*) -- One entry per differing field,
          each containing:

          - ``field`` (*str*) -- Metadata key name.
          - ``value_a`` (*str*) -- Value in *pdf_a* (empty string if absent).
          - ``value_b`` (*str*) -- Value in *pdf_b* (empty string if absent).

    Raises:
        InputError: If either path does not point to a valid PDF file.
    """
    path_a = ensure_pdf(pdf_a)
    path_b = ensure_pdf(pdf_b)

    meta_a = _metadata_dict(PdfReader(path_a))
    meta_b = _metadata_dict(PdfReader(path_b))

    all_keys = sorted(set(meta_a.keys()) | set(meta_b.keys()))

    differences: list[dict[str, str]] = []
    for key in all_keys:
        val_a = meta_a.get(key, "")
        val_b = meta_b.get(key, "")
        if val_a != val_b:
            differences.append({
                "field": key,
                "value_a": val_a,
                "value_b": val_b,
            })

    return {
        "identical": len(differences) == 0,
        "differences": differences,
    }


def compare_structure(
    pdf_a: str | Path,
    pdf_b: str | Path,
) -> dict[str, Any]:
    """Compare structural properties of two PDFs page by page.

    Structural properties include page dimensions (width/height from the
    MediaBox) and page rotation.  Pages that exist in only one document are
    flagged as missing on the other side.

    Args:
        pdf_a: Path to the first PDF file.
        pdf_b: Path to the second PDF file.

    Returns:
        A dict with:

        - **identical** (*bool*) -- ``True`` when page counts match and every
          page has the same size and rotation.
        - **pages_a** (*int*) -- Page count of *pdf_a*.
        - **pages_b** (*int*) -- Page count of *pdf_b*.
        - **page_differences** (*list[dict]*) -- One entry per page that
          differs.  Each entry contains:

          - ``page`` (*int*) -- 1-indexed page number.
          - ``differences`` (*dict*) -- Maps the property name (e.g.
            ``"width"``, ``"height"``, ``"rotation"``) to a dict with
            ``"a"`` and ``"b"`` sub-keys holding the respective values.
            For pages present in only one document the special key
            ``"missing"`` is used.

    Raises:
        InputError: If either path does not point to a valid PDF file.
    """
    path_a = ensure_pdf(pdf_a)
    path_b = ensure_pdf(pdf_b)

    reader_a = PdfReader(path_a)
    reader_b = PdfReader(path_b)

    pages_a = len(reader_a.pages)
    pages_b = len(reader_b.pages)
    max_pages = max(pages_a, pages_b)

    page_differences: list[dict[str, Any]] = []

    for i in range(max_pages):
        page_num = i + 1
        has_a = i < pages_a
        has_b = i < pages_b

        if has_a and not has_b:
            page_differences.append({
                "page": page_num,
                "differences": {
                    "missing": {"a": "present", "b": "missing"},
                },
            })
        elif has_b and not has_a:
            page_differences.append({
                "page": page_num,
                "differences": {
                    "missing": {"a": "missing", "b": "present"},
                },
            })
        else:
            props_a = _page_properties(reader_a.pages[i])
            props_b = _page_properties(reader_b.pages[i])
            diffs: dict[str, dict[str, Any]] = {}
            for prop in ("width", "height", "rotation"):
                if props_a[prop] != props_b[prop]:
                    diffs[prop] = {"a": props_a[prop], "b": props_b[prop]}
            if diffs:
                page_differences.append({
                    "page": page_num,
                    "differences": diffs,
                })

    return {
        "identical": len(page_differences) == 0,
        "pages_a": pages_a,
        "pages_b": pages_b,
        "page_differences": page_differences,
    }


# ---------------------------------------------------------------------------
# Diff report generation
# ---------------------------------------------------------------------------

def _draw_wrapped_line(
    canvas_obj: Canvas,
    text: str,
    x: float,
    y: float,
    max_width: float,
    font_name: str,
    font_size: float,
) -> float:
    """Draw a single logical line, wrapping it if it exceeds *max_width*.

    Returns the y-coordinate below the last drawn line so the caller knows
    where to continue.
    """
    canvas_obj.setFont(font_name, font_size)
    # Approximate character width for wrapping calculation
    char_width = canvas_obj.stringWidth("M", font_name, font_size)
    if char_width == 0:
        char_width = font_size * 0.6
    chars_per_line = max(1, int(max_width / char_width))

    while text:
        segment = text[:chars_per_line]
        text = text[chars_per_line:]
        canvas_obj.drawString(x, y, segment)
        y -= _LINE_HEIGHT
    return y


def generate_diff_report(
    pdf_a: str | Path,
    pdf_b: str | Path,
    output: str | Path | None = None,
) -> Path:
    """Generate a PDF report that visualises the differences between two PDFs.

    The report contains:

    * A title page summarising page counts and whether the documents are
      identical.
    * One section per page that has differences, showing a unified-diff style
      comparison with additions highlighted in green and removals in red.

    The report is created with ReportLab so it does not depend on having a
    working PDF merge pipeline.

    Args:
        pdf_a: Path to the first PDF file.
        pdf_b: Path to the second PDF file.
        output: Optional output path for the report PDF.  When ``None`` the
            file is written to ``diff_report.pdf`` in the current directory.

    Returns:
        The resolved :class:`~pathlib.Path` of the generated report.

    Raises:
        InputError: If either input path does not point to a valid PDF file.
    """
    path_a = ensure_pdf(pdf_a)
    path_b = ensure_pdf(pdf_b)
    out = output_path(output, "diff_report.pdf")

    reader_a = PdfReader(path_a)
    reader_b = PdfReader(path_b)

    text_a = _read_pages_text(reader_a)
    text_b = _read_pages_text(reader_b)

    pages_a = len(text_a)
    pages_b = len(text_b)
    max_pages = max(pages_a, pages_b)

    page_width, page_height = A4
    usable_width = page_width - 2 * _MARGIN

    c = Canvas(str(out), pagesize=A4)

    # ---- title page -------------------------------------------------------
    y = page_height - _MARGIN
    c.setFont(_FONT_NAME_BOLD, 16)
    c.setFillColor(_COLOR_HEADING)
    c.drawString(_MARGIN, y, "PDF Comparison Report")
    y -= 30

    c.setFont(_FONT_NAME, _FONT_SIZE + 1)
    c.setFillColor(_COLOR_NORMAL)
    c.drawString(_MARGIN, y, f"Document A: {path_a.name}  ({pages_a} pages)")
    y -= _LINE_HEIGHT + 2
    c.drawString(_MARGIN, y, f"Document B: {path_b.name}  ({pages_b} pages)")
    y -= _LINE_HEIGHT + 10

    # Collect per-page diffs for the body
    page_diffs: list[tuple[int, list[str]]] = []
    for i in range(max_pages):
        page_num = i + 1
        has_a = i < pages_a
        has_b = i < pages_b

        if has_a and not has_b:
            page_diffs.append((page_num, [
                f"- [Page only in Document A]",
            ]))
        elif has_b and not has_a:
            page_diffs.append((page_num, [
                f"+ [Page only in Document B]",
            ]))
        else:
            lines_a = text_a[i].splitlines(keepends=False)
            lines_b = text_b[i].splitlines(keepends=False)
            diff_lines = list(difflib.unified_diff(
                lines_a,
                lines_b,
                fromfile="A",
                tofile="B",
                lineterm="",
            ))
            if diff_lines:
                page_diffs.append((page_num, diff_lines))

    identical = len(page_diffs) == 0
    c.setFont(_FONT_NAME_BOLD, _FONT_SIZE + 1)
    if identical:
        c.setFillColor(_COLOR_ADDED)
        c.drawString(_MARGIN, y, "Result: Documents are identical.")
    else:
        c.setFillColor(_COLOR_REMOVED)
        c.drawString(
            _MARGIN, y,
            f"Result: {len(page_diffs)} page(s) with differences.",
        )
    c.setFillColor(_COLOR_NORMAL)

    if not identical:
        # ---- detail pages -------------------------------------------------
        for page_num, diff_lines in page_diffs:
            c.showPage()
            y = page_height - _MARGIN

            # Section heading
            c.setFont(_FONT_NAME_BOLD, _HEADING_SIZE)
            c.setFillColor(_COLOR_HEADING)
            c.drawString(_MARGIN, y, f"Page {page_num}")
            y -= _HEADING_SIZE + 8

            for line in diff_lines:
                # Choose colour based on diff prefix
                if line.startswith("+") and not line.startswith("+++"):
                    c.setFillColor(_COLOR_ADDED)
                elif line.startswith("-") and not line.startswith("---"):
                    c.setFillColor(_COLOR_REMOVED)
                elif line.startswith("@@"):
                    c.setFillColor(_COLOR_HEADING)
                else:
                    c.setFillColor(_COLOR_NORMAL)

                y = _draw_wrapped_line(
                    c, line, _MARGIN, y, usable_width,
                    _FONT_NAME, _FONT_SIZE,
                )

                # Start a new page if we are running out of vertical space
                if y < _MARGIN:
                    c.showPage()
                    y = page_height - _MARGIN
                    c.setFont(_FONT_NAME_BOLD, _HEADING_SIZE)
                    c.setFillColor(_COLOR_HEADING)
                    c.drawString(_MARGIN, y, f"Page {page_num} (continued)")
                    y -= _HEADING_SIZE + 8

    c.save()
    return out
