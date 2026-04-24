"""PDF hyperlink features using pypdf.

Provides functions to add, extract, and manage clickable links in PDF
documents, similar to Adobe Acrobat's link tool. Supports both external
URL links and internal page-navigation links.
"""

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf, output_path


def add_link(
    input_pdf: str | Path,
    page_num: int,
    x: float,
    y: float,
    width: float,
    height: float,
    url: str,
    output: str | Path | None = None,
    border: bool = False,
) -> Path:
    """Add a clickable URL link to a rectangular area on a PDF page.

    The link annotation is placed at the specified coordinates using the
    PDF coordinate system (origin at the bottom-left corner of the page).

    Args:
        input_pdf: Path to the source PDF file.
        page_num: Zero-indexed page number where the link will be placed.
        x: X coordinate of the bottom-left corner of the link rectangle.
        y: Y coordinate of the bottom-left corner of the link rectangle.
        width: Width of the link rectangle in points.
        height: Height of the link rectangle in points.
        url: The destination URL (e.g. ``"https://example.com"``).
        output: Path for the output PDF. If None, defaults to
            ``<input_stem>_linked.pdf``.
        border: If True, draw a visible border around the link rectangle.
            Defaults to False (invisible link).

    Returns:
        Path to the output PDF containing the new link.

    Raises:
        InputError: If the input PDF does not exist, is invalid, or the
            page number is out of range.
    """
    pdf_path = ensure_pdf(input_pdf)
    out = output_path(output, f"{pdf_path.stem}_linked.pdf")

    reader = PdfReader(pdf_path)

    if page_num < 0 or page_num >= len(reader.pages):
        raise InputError(
            f"Page number {page_num} out of range. "
            f"PDF has {len(reader.pages)} pages (0-indexed)."
        )

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    if reader.metadata:
        writer.add_metadata(reader.metadata)

    # Build the link annotation dictionary
    rect = ArrayObject([
        FloatObject(x),
        FloatObject(y),
        FloatObject(x + width),
        FloatObject(y + height),
    ])

    action = DictionaryObject({
        NameObject("/S"): NameObject("/URI"),
        NameObject("/URI"): TextStringObject(url),
    })

    border_array = ArrayObject([
        NumberObject(0),
        NumberObject(0),
        NumberObject(1 if border else 0),
    ])

    link_annotation = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/Link"),
        NameObject("/Rect"): rect,
        NameObject("/A"): action,
        NameObject("/Border"): border_array,
    })

    # Add the annotation to the target page
    target_page = writer.pages[page_num]
    if "/Annots" in target_page:
        annots = target_page["/Annots"]
        annots = annots.get_object() if hasattr(annots, "get_object") else annots
        annots.append(link_annotation)
    else:
        target_page[NameObject("/Annots")] = ArrayObject([link_annotation])

    with open(out, "wb") as f:
        writer.write(f)

    return out


def add_internal_link(
    input_pdf: str | Path,
    from_page: int,
    x: float,
    y: float,
    width: float,
    height: float,
    to_page: int,
    output: str | Path | None = None,
    border: bool = False,
) -> Path:
    """Add an internal link from one page to another within the PDF.

    Creates a clickable region on ``from_page`` that navigates the viewer
    to ``to_page`` when clicked.

    Args:
        input_pdf: Path to the source PDF file.
        from_page: Zero-indexed page number where the link will be placed.
        x: X coordinate of the bottom-left corner of the link rectangle.
        y: Y coordinate of the bottom-left corner of the link rectangle.
        width: Width of the link rectangle in points.
        height: Height of the link rectangle in points.
        to_page: Zero-indexed destination page number.
        output: Path for the output PDF. If None, defaults to
            ``<input_stem>_linked.pdf``.
        border: If True, draw a visible border around the link rectangle.
            Defaults to False (invisible link).

    Returns:
        Path to the output PDF containing the new internal link.

    Raises:
        InputError: If the input PDF does not exist, is invalid, or either
            page number is out of range.
    """
    pdf_path = ensure_pdf(input_pdf)
    out = output_path(output, f"{pdf_path.stem}_linked.pdf")

    reader = PdfReader(pdf_path)
    num_pages = len(reader.pages)

    if from_page < 0 or from_page >= num_pages:
        raise InputError(
            f"Source page {from_page} out of range. "
            f"PDF has {num_pages} pages (0-indexed)."
        )
    if to_page < 0 or to_page >= num_pages:
        raise InputError(
            f"Destination page {to_page} out of range. "
            f"PDF has {num_pages} pages (0-indexed)."
        )

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    if reader.metadata:
        writer.add_metadata(reader.metadata)

    # Build the link annotation with a GoTo destination
    rect = ArrayObject([
        FloatObject(x),
        FloatObject(y),
        FloatObject(x + width),
        FloatObject(y + height),
    ])

    # /Dest uses an explicit destination: [page_object /Fit]
    dest_page_ref = writer.pages[to_page]
    destination = ArrayObject([
        dest_page_ref,
        NameObject("/Fit"),
    ])

    border_array = ArrayObject([
        NumberObject(0),
        NumberObject(0),
        NumberObject(1 if border else 0),
    ])

    link_annotation = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/Link"),
        NameObject("/Rect"): rect,
        NameObject("/Dest"): destination,
        NameObject("/Border"): border_array,
    })

    # Add the annotation to the source page
    source_page = writer.pages[from_page]
    if "/Annots" in source_page:
        annots = source_page["/Annots"]
        annots = annots.get_object() if hasattr(annots, "get_object") else annots
        annots.append(link_annotation)
    else:
        source_page[NameObject("/Annots")] = ArrayObject([link_annotation])

    with open(out, "wb") as f:
        writer.write(f)

    return out


def extract_links(input_pdf: str | Path) -> list[dict]:
    """Extract all links from a PDF document.

    Scans every page for link annotations and returns their details,
    including both external URL links and internal page-navigation links.

    Args:
        input_pdf: Path to the PDF file to inspect.

    Returns:
        A list of dicts, each containing:
            - ``page`` (int): 1-indexed page number where the link appears.
            - ``type`` (str): Either ``"url"`` for external links or
              ``"internal"`` for links to other pages within the document.
            - ``destination`` (str | int): The URL string for external links,
              or the 1-indexed destination page number for internal links.
            - ``rect`` (dict): A dict with ``x``, ``y``, ``width``, and
              ``height`` keys describing the link's clickable area.

    Raises:
        InputError: If the input PDF does not exist or is invalid.
    """
    pdf_path = ensure_pdf(input_pdf)
    reader = PdfReader(pdf_path)
    results: list[dict] = []

    # Build a mapping from page indirect-object IDs to page numbers
    page_id_map: dict[int, int] = {}
    for idx, page in enumerate(reader.pages):
        page_obj = page.get_object() if hasattr(page, "get_object") else page
        page_id_map[id(page_obj)] = idx + 1  # 1-indexed

    for page_idx, page in enumerate(reader.pages):
        if "/Annots" not in page:
            continue

        annots = page["/Annots"]
        annots = annots.get_object() if hasattr(annots, "get_object") else annots

        for annot_ref in annots:
            annot = annot_ref.get_object() if hasattr(annot_ref, "get_object") else annot_ref

            # Only process link annotations
            subtype = annot.get("/Subtype", "")
            if subtype != "/Link":
                continue

            # Parse the rectangle
            rect_data = annot.get("/Rect")
            if rect_data is None:
                continue
            rect_array = rect_data.get_object() if hasattr(rect_data, "get_object") else rect_data
            x1 = float(rect_array[0])
            y1 = float(rect_array[1])
            x2 = float(rect_array[2])
            y2 = float(rect_array[3])
            rect = {
                "x": x1,
                "y": y1,
                "width": x2 - x1,
                "height": y2 - y1,
            }

            link_info = {
                "page": page_idx + 1,  # 1-indexed
                "rect": rect,
            }

            # Check for external URL via /A action
            if "/A" in annot:
                action = annot["/A"]
                action = action.get_object() if hasattr(action, "get_object") else action
                action_type = action.get("/S", "")

                if action_type == "/URI" and "/URI" in action:
                    link_info["type"] = "url"
                    link_info["destination"] = str(action["/URI"])
                    results.append(link_info)
                    continue

                if action_type == "/GoTo" and "/D" in action:
                    dest = action["/D"]
                    dest = dest.get_object() if hasattr(dest, "get_object") else dest
                    dest_page = _resolve_destination_page(dest, reader, page_id_map)
                    link_info["type"] = "internal"
                    link_info["destination"] = dest_page
                    results.append(link_info)
                    continue

            # Check for /Dest (explicit destination, used by internal links)
            if "/Dest" in annot:
                dest = annot["/Dest"]
                dest = dest.get_object() if hasattr(dest, "get_object") else dest
                dest_page = _resolve_destination_page(dest, reader, page_id_map)
                link_info["type"] = "internal"
                link_info["destination"] = dest_page
                results.append(link_info)

    return results


def _resolve_destination_page(
    dest,
    reader: PdfReader,
    page_id_map: dict[int, int],
) -> int:
    """Resolve a PDF destination to a 1-indexed page number.

    Handles both array-style destinations (``[page_ref /Fit ...]``) and
    named destinations.

    Args:
        dest: The destination object from the annotation.
        reader: The PdfReader instance for the document.
        page_id_map: Mapping from page object ``id()`` to 1-indexed page
            numbers.

    Returns:
        The 1-indexed page number, or 0 if the destination cannot be
        resolved.
    """
    # Array-style: [page_obj, /Fit, ...]
    if isinstance(dest, ArrayObject) and len(dest) > 0:
        page_ref = dest[0]
        page_obj = page_ref.get_object() if hasattr(page_ref, "get_object") else page_ref

        # Try direct identity match
        page_num = page_id_map.get(id(page_obj))
        if page_num is not None:
            return page_num

        # Fallback: compare against reader pages
        for idx, rp in enumerate(reader.pages):
            rp_obj = rp.get_object() if hasattr(rp, "get_object") else rp
            if rp_obj == page_obj:
                return idx + 1

    # Named string destination
    if isinstance(dest, str):
        named_dests = reader.named_destinations
        if dest in named_dests:
            named = named_dests[dest]
            if "/Page" in named:
                try:
                    return int(named["/Page"]) + 1
                except (ValueError, TypeError):
                    pass

    return 0
