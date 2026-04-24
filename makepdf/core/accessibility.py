"""PDF accessibility features using pypdf.

Provides tools for setting document language, title display preferences,
and checking basic accessibility compliance — similar to Adobe Acrobat's
accessibility panel.
"""

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    BooleanObject,
    DictionaryObject,
    NameObject,
    TextStringObject,
)

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf, output_path


def set_language(
    input_pdf: str | Path,
    language: str,
    output: str | Path | None = None,
) -> Path:
    """Set the document language in the PDF catalog.

    The language tag follows BCP 47 / ISO 639 conventions (e.g. ``"en-US"``,
    ``"de-DE"``, ``"fr-FR"``).  This value is stored in the catalog's
    ``/Lang`` entry and is used by screen readers and other assistive
    technology to select the correct pronunciation rules.

    Args:
        input_pdf: Path to the source PDF file.
        language: BCP 47 language tag (e.g. ``"en-US"``).
        output: Path for the output PDF.  If ``None``, defaults to
            ``"accessible.pdf"`` in the current directory.

    Returns:
        Path to the written PDF.

    Raises:
        InputError: If the input file is missing or not a PDF.
        ValueError: If *language* is empty.
    """
    if not language or not language.strip():
        raise ValueError("Language tag must not be empty.")

    pdf_path = ensure_pdf(input_pdf)
    out = output_path(output, pdf_path.stem + "_lang.pdf")

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    if reader.metadata:
        writer.add_metadata(reader.metadata)

    # Set /Lang on the document catalog
    writer._root_object[NameObject("/Lang")] = TextStringObject(language.strip())

    with open(out, "wb") as f:
        writer.write(f)

    return out


def get_language(input_pdf: str | Path) -> str | None:
    """Get the document language from the PDF catalog.

    Args:
        input_pdf: Path to the PDF file.

    Returns:
        The language tag string (e.g. ``"en-US"``) or ``None`` if no
        language has been set.

    Raises:
        InputError: If the input file is missing or not a PDF.
    """
    pdf_path = ensure_pdf(input_pdf)
    reader = PdfReader(pdf_path)

    lang = reader.trailer.get("/Root", {}).get("/Lang")
    if lang is not None:
        return str(lang)

    # Also try direct catalog access
    try:
        catalog = reader._trailer["/Root"].get_object()
        lang = catalog.get("/Lang")
        if lang is not None:
            return str(lang)
    except Exception:
        pass

    return None


def set_title_display(
    input_pdf: str | Path,
    display_title: bool = True,
    output: str | Path | None = None,
) -> Path:
    """Set whether the title bar shows the document title or the filename.

    When *display_title* is ``True`` the viewer should display the value of
    the ``/Title`` metadata entry in its title bar instead of the filename.
    This is controlled by the ``/ViewerPreferences`` dictionary's
    ``/DisplayDocTitle`` boolean.

    Args:
        input_pdf: Path to the source PDF file.
        display_title: ``True`` to display the document title, ``False``
            to display the filename.
        output: Path for the output PDF.  If ``None``, defaults to a name
            derived from the input file.

    Returns:
        Path to the written PDF.

    Raises:
        InputError: If the input file is missing or not a PDF.
    """
    pdf_path = ensure_pdf(input_pdf)
    out = output_path(output, pdf_path.stem + "_title_display.pdf")

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    if reader.metadata:
        writer.add_metadata(reader.metadata)

    # Build or update /ViewerPreferences
    root = writer._root_object
    viewer_prefs = root.get("/ViewerPreferences")

    if viewer_prefs is None:
        viewer_prefs = DictionaryObject()

    # Ensure we have a mutable copy
    if not isinstance(viewer_prefs, DictionaryObject):
        new_prefs = DictionaryObject()
        try:
            resolved = viewer_prefs.get_object()
            if hasattr(resolved, "keys"):
                for key in resolved:
                    new_prefs[NameObject(key)] = resolved[key]
        except Exception:
            pass
        viewer_prefs = new_prefs

    viewer_prefs[NameObject("/DisplayDocTitle")] = BooleanObject(display_title)
    root[NameObject("/ViewerPreferences")] = viewer_prefs

    with open(out, "wb") as f:
        writer.write(f)

    return out


def check_accessibility(input_pdf: str | Path) -> dict:
    """Check a PDF for basic accessibility issues.

    Inspects the document for common accessibility requirements such as a
    declared language, document title, tagged structure, and bookmarks.
    Returns a summary dictionary with findings and a simple quality score.

    The returned dictionary contains:

    - ``has_language`` (bool): Whether a ``/Lang`` entry exists.
    - ``language`` (str | None): The language tag, if present.
    - ``has_title`` (bool): Whether a ``/Title`` metadata entry exists.
    - ``title`` (str | None): The title string, if present.
    - ``displays_title`` (bool): Whether ``/DisplayDocTitle`` is set to
      ``true``.
    - ``is_tagged`` (bool): Whether the PDF declares a ``/MarkInfo``
      dictionary with ``/Marked`` set to ``true``.
    - ``has_bookmarks`` (bool): Whether the document contains an outline
      (bookmarks / table of contents).
    - ``page_count`` (int): Number of pages in the document.
    - ``issues`` (list[str]): Human-readable descriptions of accessibility
      problems found.
    - ``score`` (str): One of ``"good"``, ``"fair"``, or ``"poor"``.

    Args:
        input_pdf: Path to the PDF file to check.

    Returns:
        A dictionary with the accessibility audit results described above.

    Raises:
        InputError: If the input file is missing or not a PDF.
    """
    pdf_path = ensure_pdf(input_pdf)
    reader = PdfReader(pdf_path)

    issues: list[str] = []

    # --- Language ---
    language = get_language(pdf_path)
    has_language = language is not None
    if not has_language:
        issues.append("No document language set. Screen readers may mispronounce text.")

    # --- Title ---
    title: str | None = None
    if reader.metadata and reader.metadata.title:
        title = reader.metadata.title
    has_title = bool(title)
    if not has_title:
        issues.append("No document title in metadata. Assistive technology cannot announce the document name.")

    # --- DisplayDocTitle ---
    displays_title = False
    try:
        catalog = reader._trailer["/Root"].get_object()
        vp = catalog.get("/ViewerPreferences")
        if vp is not None:
            vp_obj = vp.get_object() if hasattr(vp, "get_object") else vp
            ddt = vp_obj.get("/DisplayDocTitle")
            if ddt is not None:
                displays_title = bool(ddt)
    except Exception:
        pass

    if has_title and not displays_title:
        issues.append("Document has a title but is not configured to display it in the title bar.")

    # --- Tagged PDF ---
    is_tagged = False
    try:
        catalog = reader._trailer["/Root"].get_object()
        mark_info = catalog.get("/MarkInfo")
        if mark_info is not None:
            mi_obj = mark_info.get_object() if hasattr(mark_info, "get_object") else mark_info
            marked = mi_obj.get("/Marked")
            if marked is not None:
                is_tagged = bool(marked)
    except Exception:
        pass

    if not is_tagged:
        issues.append("PDF is not tagged. Document structure is unavailable to assistive technology.")

    # --- Bookmarks / Outlines ---
    has_bookmarks = False
    try:
        outlines = reader.outline
        if outlines and len(outlines) > 0:
            has_bookmarks = True
    except Exception:
        pass

    page_count = len(reader.pages)
    if not has_bookmarks and page_count > 1:
        issues.append("No bookmarks found. Navigation may be difficult for long documents.")

    # --- Score ---
    total_checks = 5  # language, title, displays_title, tagged, bookmarks
    passed = sum([
        has_language,
        has_title,
        displays_title if has_title else False,
        is_tagged,
        has_bookmarks,
    ])

    if passed >= 4:
        score = "good"
    elif passed >= 2:
        score = "fair"
    else:
        score = "poor"

    return {
        "has_language": has_language,
        "language": language,
        "has_title": has_title,
        "title": title,
        "displays_title": displays_title,
        "is_tagged": is_tagged,
        "has_bookmarks": has_bookmarks,
        "page_count": page_count,
        "issues": issues,
        "score": score,
    }
