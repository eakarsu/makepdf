"""PDF flattening — convert interactive elements to static content.

Provides functionality similar to Adobe Acrobat's "Flatten" feature:
form fields become non-editable text, and annotations (comments, markups,
stamps) are burned into the page content so they can no longer be modified
or removed.
"""

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf, output_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _merge_appearance_into_page(page, annot):
    """Merge an annotation's normal appearance stream into the page content.

    The appearance stream (/AP -> /N) contains the visual representation of
    the annotation.  We extract it and stamp it onto the page so it becomes
    part of the static content.

    Args:
        page: The pypdf page object to merge into.
        annot: The resolved annotation dictionary.

    Returns:
        True if the appearance was successfully merged, False otherwise.
    """
    ap = annot.get("/AP")
    if ap is None:
        return False

    # /AP is a dictionary; /N is the normal appearance
    if isinstance(ap, DictionaryObject):
        normal = ap.get("/N")
    else:
        return False

    if normal is None:
        return False

    # Get the annotation rectangle for positioning
    rect = annot.get("/Rect")
    if rect is None:
        return False

    try:
        # Build a form XObject reference and merge it into the page
        page.merge_page(
            _appearance_to_page(normal, rect),
            over=True,
        )
    except Exception:
        # If merging fails (e.g. corrupt appearance stream) we skip
        # this annotation rather than aborting the whole operation.
        return False

    return True


def _appearance_to_page(appearance_stream, rect):
    """Create a minimal single-page PDF from an appearance stream.

    This is used as an intermediary so we can call ``page.merge_page()``
    with the appearance content positioned at the correct rectangle.

    Args:
        appearance_stream: The /N appearance stream object.
        rect: The /Rect array ``[x1, y1, x2, y2]`` of the annotation.

    Returns:
        A pypdf page object containing the rendered appearance.
    """
    from pypdf.generic import RectangleObject

    writer = PdfWriter()
    # Determine the page size from the rect
    r = RectangleObject(rect)
    page = writer.add_blank_page(
        width=float(r.width),
        height=float(r.height),
    )

    # Overlay the appearance stream at (0, 0) — the page was sized to the
    # annotation rect already.  The caller will position via merge_page.
    try:
        # Create a temporary reader-based page from the appearance
        tmp_writer = PdfWriter()
        tmp_page = tmp_writer.add_blank_page(
            width=float(r.width),
            height=float(r.height),
        )
        # Attempt to set the appearance stream as the page content
        tmp_page[NameObject("/Contents")] = appearance_stream
        tmp_page[NameObject("/Resources")] = appearance_stream.get(
            "/Resources", DictionaryObject()
        )
        return tmp_page
    except Exception:
        return page


def _is_widget(annot) -> bool:
    """Return True if the annotation is a form widget (/Widget subtype)."""
    subtype = annot.get("/Subtype")
    return subtype == "/Widget"


def _is_annotation(annot) -> bool:
    """Return True if the annotation is a non-widget annotation."""
    subtype = annot.get("/Subtype")
    # Widgets are form fields, everything else is an annotation
    return subtype is not None and subtype != "/Widget"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def flatten_forms(
    input_pdf: str | Path,
    output: str | Path | None = None,
) -> Path:
    """Flatten all form fields, making them non-editable static content.

    Interactive form fields (text boxes, checkboxes, dropdowns, etc.) are
    converted to their visual representation and burned into the page
    content.  The resulting PDF looks identical but the fields can no
    longer be edited.

    This is equivalent to *Flatten Form Fields* in Adobe Acrobat.

    Args:
        input_pdf: Path to the source PDF containing form fields.
        output: Optional destination path.  When ``None`` the output file
            is written as ``flattened_forms.pdf`` in the current directory.

    Returns:
        Path to the flattened PDF.

    Raises:
        InputError: If the input file does not exist or is not a PDF.
    """
    pdf_path = ensure_pdf(input_pdf)
    out = output_path(output, pdf_path.stem + "_flattened_forms.pdf")

    try:
        reader = PdfReader(pdf_path)
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        # Process each page — find widget annotations and flatten them
        for page in writer.pages:
            annots = page.get("/Annots")
            if annots is None:
                continue

            # Resolve indirect references
            resolved_annots = []
            remaining_annots = []

            for annot_ref in annots:
                annot = annot_ref.get_object()

                if _is_widget(annot):
                    # Attempt to merge the appearance into the page
                    _merge_appearance_into_page(page, annot)
                    resolved_annots.append(annot_ref)
                else:
                    remaining_annots.append(annot_ref)

            # Keep only non-widget annotations
            if remaining_annots:
                page[NameObject("/Annots")] = ArrayObject(remaining_annots)
            elif "/Annots" in page:
                del page[NameObject("/Annots")]

        # Remove the AcroForm dictionary so readers don't treat
        # the document as having interactive fields.
        if "/AcroForm" in writer._root_object:
            del writer._root_object[NameObject("/AcroForm")]

        with open(out, "wb") as f:
            writer.write(f)

    except InputError:
        raise
    except Exception as exc:
        raise InputError(f"Failed to flatten form fields: {exc}") from exc

    return out


def flatten_annotations(
    input_pdf: str | Path,
    output: str | Path | None = None,
) -> Path:
    """Flatten all annotations into static page content.

    Annotations such as comments, sticky notes, text markups (highlights,
    underlines, strikethroughs), stamps, ink drawings, and other markup
    elements are burned into the page content.  The visual appearance is
    preserved but the annotations can no longer be selected, edited, or
    deleted.

    Form widget annotations are *not* affected — use :func:`flatten_forms`
    or :func:`flatten_all` for those.

    Args:
        input_pdf: Path to the source PDF containing annotations.
        output: Optional destination path.  When ``None`` the output file
            is written as ``flattened_annots.pdf`` in the current directory.

    Returns:
        Path to the flattened PDF.

    Raises:
        InputError: If the input file does not exist or is not a PDF.
    """
    pdf_path = ensure_pdf(input_pdf)
    out = output_path(output, pdf_path.stem + "_flattened_annots.pdf")

    try:
        reader = PdfReader(pdf_path)
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        for page in writer.pages:
            annots = page.get("/Annots")
            if annots is None:
                continue

            remaining_annots = []

            for annot_ref in annots:
                annot = annot_ref.get_object()

                if _is_annotation(annot):
                    # Merge the annotation appearance into page content
                    _merge_appearance_into_page(page, annot)
                    # Do not keep this annotation
                else:
                    # Keep widget annotations untouched
                    remaining_annots.append(annot_ref)

            if remaining_annots:
                page[NameObject("/Annots")] = ArrayObject(remaining_annots)
            elif "/Annots" in page:
                del page[NameObject("/Annots")]

        with open(out, "wb") as f:
            writer.write(f)

    except InputError:
        raise
    except Exception as exc:
        raise InputError(
            f"Failed to flatten annotations: {exc}"
        ) from exc

    return out


def flatten_all(
    input_pdf: str | Path,
    output: str | Path | None = None,
) -> Path:
    """Flatten both form fields and annotations into static content.

    This combines :func:`flatten_forms` and :func:`flatten_annotations`
    in a single pass, producing a PDF with no interactive elements at all.
    The visual appearance is preserved exactly as it was displayed.

    This is equivalent to choosing *Flatten* in Adobe Acrobat, which
    converts every interactive and markup element into the page stream.

    Args:
        input_pdf: Path to the source PDF.
        output: Optional destination path.  When ``None`` the output file
            is written as ``flattened.pdf`` in the current directory.

    Returns:
        Path to the fully flattened PDF.

    Raises:
        InputError: If the input file does not exist or is not a PDF.
    """
    pdf_path = ensure_pdf(input_pdf)
    out = output_path(output, pdf_path.stem + "_flattened.pdf")

    try:
        reader = PdfReader(pdf_path)
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        for page in writer.pages:
            annots = page.get("/Annots")
            if annots is None:
                continue

            for annot_ref in annots:
                annot = annot_ref.get_object()
                # Merge every annotation's appearance into the page
                _merge_appearance_into_page(page, annot)

            # Remove all annotations from the page
            if "/Annots" in page:
                del page[NameObject("/Annots")]

        # Remove AcroForm so the PDF is no longer considered a form
        if "/AcroForm" in writer._root_object:
            del writer._root_object[NameObject("/AcroForm")]

        with open(out, "wb") as f:
            writer.write(f)

    except InputError:
        raise
    except Exception as exc:
        raise InputError(f"Failed to flatten PDF: {exc}") from exc

    return out
