"""PDF page label features (page numbering schemes).

This module allows setting and retrieving page labels on a PDF, similar
to Adobe Acrobat's page numbering settings.  Page labels control how page
numbers are displayed in the viewer's toolbar and thumbnails -- for example
using Roman numerals for a preface followed by Arabic numerals for the body.

The PDF specification stores page labels in the document catalog under the
``/PageLabels`` entry, which contains a number tree (``/Nums`` array) of
page-index / label-dict pairs.
"""

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf, output_path as resolve_output

# ── Style mapping ────────────────────────────────────────────────────────────

# Friendly name  →  PDF /S value
_STYLE_TO_PDF = {
    "decimal": NameObject("/D"),
    "roman_lower": NameObject("/r"),
    "roman_upper": NameObject("/R"),
    "alpha_lower": NameObject("/a"),
    "alpha_upper": NameObject("/A"),
    "none": None,  # omit /S entirely → no numbering, prefix only
}

# PDF /S value  →  friendly name
_PDF_TO_STYLE = {
    "/D": "decimal",
    "/r": "roman_lower",
    "/R": "roman_upper",
    "/a": "alpha_lower",
    "/A": "alpha_upper",
}


# ── Public API ───────────────────────────────────────────────────────────────


def set_page_labels(
    input_pdf: str | Path,
    labels: list[dict],
    output: str | Path | None = None,
) -> Path:
    """Set page labels (numbering schemes) on a PDF.

    Page labels control how page numbers are presented to the user in a
    PDF viewer.  Multiple ranges can be defined so that, for example, the
    first four pages use lower-case Roman numerals while the rest use
    standard decimal numbering.

    Args:
        input_pdf: Path to the source PDF.
        labels: A list of label-range dictionaries, each containing:

            * ``start_page`` (int) -- 0-indexed page where this range begins.
            * ``style`` (str) -- One of ``"decimal"``, ``"roman_lower"``,
              ``"roman_upper"``, ``"alpha_lower"``, ``"alpha_upper"``, or
              ``"none"`` (prefix only, no number).
            * ``prefix`` (str, optional) -- A string prepended to every
              page number in this range (e.g. ``"A-"`` → ``"A-1"``,
              ``"A-2"``).
            * ``first_number`` (int, optional) -- The starting numeric
              value for this range.  Defaults to ``1``.

        output: Destination path.  If *None*, a default name is generated
            from the input filename.

    Returns:
        Path to the output PDF with the new page labels applied.

    Raises:
        InputError: If the input is not a valid PDF or *labels* contains
            invalid data.

    Example::

        set_page_labels("thesis.pdf", [
            {"start_page": 0, "style": "roman_lower"},
            {"start_page": 4, "style": "decimal", "prefix": "", "first_number": 1},
        ])
    """
    pdf_path = ensure_pdf(input_pdf)
    out_path = resolve_output(output, pdf_path.stem + "_labeled.pdf")

    if not labels:
        raise InputError("labels list must not be empty.")

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    # Copy all pages and metadata
    for page in reader.pages:
        writer.add_page(page)
    if reader.metadata is not None:
        writer.add_metadata(reader.metadata)

    page_count = len(reader.pages)

    # Build the /Nums array: [page_index, label_dict, page_index, label_dict, …]
    nums = ArrayObject()

    for entry in labels:
        # ── Validate entry ------------------------------------------------
        if "start_page" not in entry:
            raise InputError("Each label entry must include 'start_page'.")
        start_page = entry["start_page"]
        if not isinstance(start_page, int) or start_page < 0:
            raise InputError(
                f"'start_page' must be a non-negative integer, got {start_page!r}."
            )
        if start_page >= page_count:
            raise InputError(
                f"'start_page' {start_page} exceeds page count ({page_count})."
            )

        style = entry.get("style", "decimal")
        if style not in _STYLE_TO_PDF:
            raise InputError(
                f"Unknown style '{style}'. Choose from: {list(_STYLE_TO_PDF.keys())}"
            )

        prefix = entry.get("prefix")
        first_number = entry.get("first_number", 1)
        if not isinstance(first_number, int) or first_number < 0:
            raise InputError(
                f"'first_number' must be a non-negative integer, got {first_number!r}."
            )

        # ── Build the label dictionary ------------------------------------
        label_dict = DictionaryObject()

        pdf_style = _STYLE_TO_PDF[style]
        if pdf_style is not None:
            label_dict[NameObject("/S")] = pdf_style

        if prefix is not None:
            label_dict[NameObject("/P")] = TextStringObject(prefix)

        if first_number != 1:
            label_dict[NameObject("/St")] = NumberObject(first_number)

        nums.append(NumberObject(start_page))
        nums.append(label_dict)

    # Attach to the catalog
    page_labels = DictionaryObject()
    page_labels[NameObject("/Nums")] = nums
    writer._root_object[NameObject("/PageLabels")] = page_labels

    with open(out_path, "wb") as f:
        writer.write(f)

    return out_path


def get_page_labels(input_pdf: str | Path) -> list[dict]:
    """Extract the current page label configuration from a PDF.

    Args:
        input_pdf: Path to the PDF file.

    Returns:
        A list of label-range dictionaries (same structure accepted by
        :func:`set_page_labels`).  Returns an empty list if the PDF has
        no page labels defined.

    Raises:
        InputError: If the input is not a valid PDF.

    Example::

        labels = get_page_labels("thesis.pdf")
        # [
        #     {"start_page": 0, "style": "roman_lower", "first_number": 1},
        #     {"start_page": 4, "style": "decimal", "first_number": 1},
        # ]
    """
    pdf_path = ensure_pdf(input_pdf)
    reader = PdfReader(pdf_path)

    # Navigate to /Root -> /PageLabels -> /Nums
    root = reader.trailer["/Root"].get_object()
    if "/PageLabels" not in root:
        return []

    page_labels_obj = root["/PageLabels"].get_object()
    if "/Nums" not in page_labels_obj:
        return []

    nums = page_labels_obj["/Nums"]
    # Resolve indirect reference if needed
    if hasattr(nums, "get_object"):
        nums = nums.get_object()

    results: list[dict] = []

    # The /Nums array contains pairs: [page_index, label_dict, …]
    for i in range(0, len(nums), 2):
        page_index = nums[i]
        if hasattr(page_index, "get_object"):
            page_index = page_index.get_object()
        page_index = int(page_index)

        label_obj = nums[i + 1]
        if hasattr(label_obj, "get_object"):
            label_obj = label_obj.get_object()

        entry: dict = {"start_page": page_index}

        # /S  →  style
        s_val = label_obj.get("/S")
        if s_val is not None:
            s_str = str(s_val)
            entry["style"] = _PDF_TO_STYLE.get(s_str, "decimal")
        else:
            entry["style"] = "none"

        # /P  →  prefix
        p_val = label_obj.get("/P")
        if p_val is not None:
            entry["prefix"] = str(p_val)

        # /St  →  first_number
        st_val = label_obj.get("/St")
        entry["first_number"] = int(st_val) if st_val is not None else 1

        results.append(entry)

    return results
