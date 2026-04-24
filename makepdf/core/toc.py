"""Table-of-contents generation, extraction, and bookmark management."""

import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf, output_path


# ── public API ───────────────────────────────────────────────────────────


def generate_toc(
    input_pdf: str | Path,
    entries: list[dict],
    output: str | Path | None = None,
) -> Path:
    """Generate a Table of Contents page and prepend it to *input_pdf*.

    Parameters
    ----------
    entries : list[dict]
        Each dict has keys:
        - ``"title"`` (str)
        - ``"page"``  (int, 1-based page number in the *original* PDF)
        - ``"level"`` (int, 0 / 1 / 2 — controls indentation)
    """
    pdf_path = ensure_pdf(input_pdf)
    out = output_path(output, pdf_path.stem + "_toc.pdf")
    reader = PdfReader(str(pdf_path))

    # Determine TOC page size from the first page of the source PDF
    first_box = reader.pages[0].mediabox
    page_width = float(first_box.width)
    page_height = float(first_box.height)

    toc_buf = _build_toc_pages(entries, page_width, page_height)
    toc_reader = PdfReader(toc_buf)

    writer = PdfWriter()

    # Prepend TOC pages
    for toc_page in toc_reader.pages:
        writer.add_page(toc_page)

    # Append original pages
    for page in reader.pages:
        writer.add_page(page)

    with open(out, "wb") as f:
        writer.write(f)

    return out


def extract_toc(input_pdf: str | Path) -> list[dict]:
    """Extract bookmarks / outlines from a PDF.

    Returns a flat list of ``{"title": str, "page": int, "level": int}``
    dicts.  Page numbers are 1-based.
    """
    pdf_path = ensure_pdf(input_pdf)
    reader = PdfReader(str(pdf_path))

    results: list[dict] = []
    outlines = reader.outline
    if not outlines:
        return results

    _walk_outlines(reader, outlines, results, level=0)
    return results


def add_bookmarks(
    input_pdf: str | Path,
    entries: list[dict],
    output: str | Path | None = None,
) -> Path:
    """Add bookmarks (outlines) to a PDF.

    Parameters
    ----------
    entries : list[dict]
        Each dict has keys ``"title"`` (str), ``"page"`` (int, 1-based),
        and ``"level"`` (int, 0 / 1 / 2).
    """
    pdf_path = ensure_pdf(input_pdf)
    out = output_path(output, pdf_path.stem + "_bookmarked.pdf")

    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    writer.clone_reader_document_root(reader)

    # Stack of (level, outline_item) so children can reference their parent
    parent_stack: list[tuple[int, object]] = []

    for entry in entries:
        title = entry["title"]
        page_num = int(entry["page"]) - 1  # pypdf uses 0-based
        level = int(entry.get("level", 0))

        if page_num < 0 or page_num >= len(reader.pages):
            raise InputError(
                f"Bookmark page {entry['page']} out of range "
                f"(PDF has {len(reader.pages)} pages)"
            )

        # Pop stack until we find a suitable parent
        while parent_stack and parent_stack[-1][0] >= level:
            parent_stack.pop()

        parent = parent_stack[-1][1] if parent_stack else None
        item = writer.add_outline_item(title, page_num, parent=parent)
        parent_stack.append((level, item))

    with open(out, "wb") as f:
        writer.write(f)

    return out


# ── internal helpers ─────────────────────────────────────────────────────


def _build_toc_pages(
    entries: list[dict],
    page_width: float,
    page_height: float,
) -> io.BytesIO:
    """Render one or more TOC pages into a BytesIO PDF buffer."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))

    margin_left = 1.0 * inch
    margin_right = 1.0 * inch
    margin_top = 1.0 * inch
    margin_bottom = 1.0 * inch
    usable_width = page_width - margin_left - margin_right

    indent_per_level = 0.3 * inch
    title_font = "Helvetica-Bold"
    entry_font = "Helvetica"
    title_size = 18
    entry_sizes = {0: 12, 1: 11, 2: 10}
    line_spacing = 18  # points between entries

    y = page_height - margin_top

    # Title
    c.setFont(title_font, title_size)
    c.drawString(margin_left, y, "Table of Contents")
    y -= title_size + 12  # gap after title

    for entry in entries:
        level = int(entry.get("level", 0))
        title = entry["title"]
        page_num_str = str(entry["page"])
        font_size = entry_sizes.get(level, 10)

        # Start new page if needed
        if y < margin_bottom:
            c.showPage()
            y = page_height - margin_top

        indent = indent_per_level * level
        text_x = margin_left + indent

        c.setFont(entry_font, font_size)

        # Measure widths
        title_width = c.stringWidth(title, entry_font, font_size)
        page_num_width = c.stringWidth(page_num_str, entry_font, font_size)
        dot_width = c.stringWidth(". ", entry_font, font_size)

        available = usable_width - indent - page_num_width - 8  # 8pt gap

        # Truncate title if it's too long
        display_title = title
        if title_width > available - dot_width * 3:
            while (
                c.stringWidth(display_title + "...", entry_font, font_size)
                > available - dot_width * 3
                and len(display_title) > 1
            ):
                display_title = display_title[:-1]
            display_title += "..."
            title_width = c.stringWidth(display_title, entry_font, font_size)

        # Draw title
        c.drawString(text_x, y, display_title)

        # Draw dot leaders
        dots_start = text_x + title_width + 4
        dots_end = margin_left + usable_width - page_num_width - 4
        dot_char = "."
        single_dot_w = c.stringWidth(dot_char, entry_font, font_size)
        if dots_end > dots_start + single_dot_w * 2:
            dot_x = dots_start
            while dot_x < dots_end:
                c.drawString(dot_x, y, dot_char)
                dot_x += single_dot_w * 1.5  # spaced dots

        # Draw page number right-aligned
        page_x = margin_left + usable_width - page_num_width
        c.drawString(page_x, y, page_num_str)

        y -= line_spacing

    c.save()
    buf.seek(0)
    return buf


def _walk_outlines(
    reader: PdfReader,
    outlines: list,
    results: list[dict],
    level: int,
) -> None:
    """Recursively walk the outline tree and append flat entries to *results*."""
    for item in outlines:
        if isinstance(item, list):
            # Nested children
            _walk_outlines(reader, item, results, level + 1)
        else:
            # item is a Destination object
            try:
                page_number = reader.get_destination_page_number(item)
            except Exception:
                # Fallback: try resolving via page mapping
                page_number = _resolve_page_number(reader, item)

            results.append(
                {
                    "title": str(item.title),
                    "page": page_number + 1,  # convert to 1-based
                    "level": level,
                }
            )


def _resolve_page_number(reader: PdfReader, destination) -> int:
    """Best-effort page number resolution for a Destination object."""
    try:
        if hasattr(destination, "page") and destination.page is not None:
            page_obj = destination.page.get_object()
            for i, p in enumerate(reader.pages):
                if p.get_object() == page_obj:
                    return i
    except Exception:
        pass
    return 0
