"""Irreversible PDF redaction with post-save recovery-path verification.

Redaction is deliberately implemented with PyMuPDF's native redaction
annotations.  Painting a rectangle into a content stream is *not* redaction:
the original glyphs, images, attachments, metadata, or an incremental revision
can otherwise remain recoverable.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Sequence

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf, output_path


def _fitz():
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - packaging guard
        raise InputError(
            "Secure redaction requires PyMuPDF. Install the declared project "
            "dependencies before using redaction."
        ) from exc
    return fitz


def _validate_fill_color(fill_color: tuple) -> tuple[float, float, float]:
    if (
        not isinstance(fill_color, (tuple, list))
        or len(fill_color) != 3
        or not all(isinstance(value, (int, float)) for value in fill_color)
        or not all(0 <= value <= 1 for value in fill_color)
    ):
        raise InputError("fill_color must contain three numeric values between 0 and 1.")
    return tuple(float(value) for value in fill_color)


def _assert_safe_source(doc) -> None:
    """Fail closed when redaction would silently invalidate a signature."""
    for page in doc:
        for widget in page.widgets() or ():
            if getattr(widget, "field_type_string", "").lower() == "signature":
                raise InputError(
                    "Signed PDFs must be reviewed and re-signed through an approved "
                    "signature workflow after redaction; this operation refuses to "
                    "silently invalidate a signature."
                )


def _apply_page_redactions(page) -> bool:
    """Remove covered text, raster images, and vector graphics."""
    try:
        return bool(page.apply_redactions(images=1, graphics=1, text=0))
    except TypeError:  # PyMuPDF versions before the graphics argument
        return bool(page.apply_redactions(images=1, text=0))


def _scrub_document(doc) -> None:
    """Remove non-page recovery channels before a fresh, non-incremental save."""
    # Document.scrub handles embedded files, hidden text, JavaScript, metadata,
    # XML metadata, thumbnails, and redaction remnants in one supported API.
    doc.scrub(
        attached_files=True,
        clean_pages=True,
        embedded_files=True,
        hidden_text=True,
        javascript=True,
        metadata=True,
        redactions=True,
        redact_images=1,
        remove_links=False,
        reset_fields=True,
        reset_responses=True,
        thumbnails=True,
        xml_metadata=True,
    )
    doc.set_metadata({})
    if doc.xref_xml_metadata():
        doc.del_xml_metadata()


def _save_sanitized(doc, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    # A new file with maximum garbage collection discards incremental history,
    # unreachable objects, duplicate streams, and orphaned attachment objects.
    doc.save(
        str(destination),
        incremental=False,
        garbage=4,
        clean=True,
        deflate=True,
        deflate_images=True,
        deflate_fonts=True,
        encryption=0,
    )


def verify_redaction(
    pdf_path: str | Path,
    forbidden_terms: Iterable[str] = (),
) -> dict[str, int]:
    """Verify sanitized structure and absence of case-insensitive terms.

    Verification inspects extracted page text, file bytes, metadata, XML
    metadata, embedded files, and incremental-update markers.  It cannot prove
    that a caller selected the correct rectangle; that remains a human review
    responsibility and is why redaction reports should retain the requested
    coordinates outside the sanitized PDF.
    """
    fitz = _fitz()
    path = ensure_pdf(pdf_path)
    raw = path.read_bytes()
    raw_lower = raw.lower()

    if raw.count(b"%%EOF") != 1 or b"/prev" in raw_lower:
        raise InputError("Redaction verification found recoverable incremental history.")

    terms = [term.strip() for term in forbidden_terms if term and term.strip()]
    with fitz.open(str(path)) as doc:
        if doc.needs_pass:
            raise InputError("Redacted output unexpectedly requires a password.")
        if doc.embfile_count():
            raise InputError("Redaction verification found an embedded attachment.")
        metadata_blob = " ".join(str(value or "") for value in doc.metadata.values())
        xml_blob = doc.get_xml_metadata() or ""
        page_text = "\n".join(page.get_text("text") for page in doc)
        searchable = f"{metadata_blob}\n{xml_blob}\n{page_text}".casefold()
        for term in terms:
            folded = term.casefold()
            if folded in searchable:
                raise InputError(f"Redaction verification found forbidden text: {term!r}.")
            encoded = term.encode("utf-8", errors="ignore").lower()
            if encoded and encoded in raw_lower:
                raise InputError(f"Redaction verification found recoverable bytes: {term!r}.")

        return {
            "pages": doc.page_count,
            "embedded_files": doc.embfile_count(),
            "incremental_revisions": 0,
            "forbidden_terms": len(terms),
        }


def _finish(doc, destination: Path, forbidden_terms: Iterable[str]) -> Path:
    _scrub_document(doc)
    _save_sanitized(doc, destination)
    verify_redaction(destination, forbidden_terms)
    return destination


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
    """Permanently remove all content intersecting a rectangular region.

    Coordinates retain the historic public API: points from the PDF's
    bottom-left origin.  ``page_num`` is zero-indexed.
    """
    fitz = _fitz()
    source = ensure_pdf(input_pdf)
    color = _validate_fill_color(fill_color)
    if width <= 0 or height <= 0:
        raise InputError("width and height must be positive.")

    destination = output_path(output, source.stem + "_redacted.pdf")
    with fitz.open(str(source)) as doc:
        _assert_safe_source(doc)
        if not isinstance(page_num, int) or not 0 <= page_num < doc.page_count:
            raise InputError(
                f"page_num must be between 0 and {doc.page_count - 1}; got {page_num}."
            )
        page = doc[page_num]
        top = page.rect.height - y - height
        rect = fitz.Rect(x, top, x + width, top + height)
        if rect.is_empty or not rect.intersects(page.rect):
            raise InputError("Redaction rectangle does not intersect the selected page.")
        rect &= page.rect
        page.add_redact_annot(rect, fill=color, cross_out=False)
        _apply_page_redactions(page)
        return _finish(doc, destination, ())


def redact_text(
    input_pdf: str | Path,
    search_term: str,
    output: str | Path | None = None,
    fill_color: tuple[float, float, float] = (0, 0, 0),
    pages: list[int] | None = None,
) -> Path:
    """Permanently remove every occurrence of a plain-text term."""
    fitz = _fitz()
    source = ensure_pdf(input_pdf)
    color = _validate_fill_color(fill_color)
    if not search_term or not search_term.strip():
        raise InputError("search_term must not be empty.")

    destination = output_path(output, source.stem + "_redacted.pdf")
    with fitz.open(str(source)) as doc:
        _assert_safe_source(doc)
        if pages is None:
            targets = set(range(doc.page_count))
        else:
            if any(not isinstance(page, int) or not 1 <= page <= doc.page_count for page in pages):
                raise InputError(f"Page numbers must be between 1 and {doc.page_count}.")
            targets = {page - 1 for page in pages}

        count = 0
        for index in targets:
            page = doc[index]
            rectangles = page.search_for(search_term)
            for rect in rectangles:
                page.add_redact_annot(rect, fill=color, cross_out=False)
            if rectangles:
                _apply_page_redactions(page)
                count += len(rectangles)
        if not count:
            raise InputError(f"Search term {search_term!r} was not found in the specified pages.")
        return _finish(doc, destination, (search_term,))


def search_and_redact(
    input_pdf: str | Path,
    patterns: Sequence[str],
    output: str | Path | None = None,
    fill_color: tuple[float, float, float] = (0, 0, 0),
) -> Path:
    """Permanently remove all extracted-text matches for regex patterns."""
    fitz = _fitz()
    source = ensure_pdf(input_pdf)
    color = _validate_fill_color(fill_color)
    if not patterns:
        raise InputError("patterns must contain at least one regex pattern.")
    try:
        compiled = [re.compile(pattern) for pattern in patterns]
    except re.error as exc:
        raise InputError(f"Invalid regex pattern: {exc}") from exc

    destination = output_path(output, source.stem + "_redacted.pdf")
    forbidden: set[str] = set()
    count = 0
    with fitz.open(str(source)) as doc:
        _assert_safe_source(doc)
        for page in doc:
            page_text = page.get_text("text")
            page_count = 0
            for regex in compiled:
                for match in regex.finditer(page_text):
                    term = match.group(0)
                    if not term:
                        continue
                    rectangles = page.search_for(term)
                    for rect in rectangles:
                        page.add_redact_annot(rect, fill=color, cross_out=False)
                    page_count += len(rectangles)
                    forbidden.add(term)
            if page_count:
                _apply_page_redactions(page)
                count += page_count
        if not count:
            raise InputError("No matches found for the supplied patterns in the PDF.")
        return _finish(doc, destination, forbidden)
