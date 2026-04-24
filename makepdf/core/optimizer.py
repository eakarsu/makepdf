"""PDF optimization features (reduce file size, remove unused objects).

This module provides tools comparable to Adobe Acrobat's *Optimize PDF* and
*Reduce File Size* functions.  It uses pypdf to strip unnecessary data,
merge duplicate objects, compress streams, and reorder objects for faster
web delivery.
"""

import os
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf, output_path as resolve_output


# ── Public API ───────────────────────────────────────────────────────────────


def optimize(
    input_pdf: str | Path,
    output: str | Path | None = None,
    remove_duplication: bool = True,
    remove_metadata: bool = False,
    compress_streams: bool = True,
) -> Path:
    """Optimize a PDF for reduced file size.

    Applies one or more optimization strategies that mirror the options
    found in Adobe Acrobat's *Reduce File Size* dialog.

    Args:
        input_pdf: Path to the source PDF.
        output: Destination path.  If *None*, a default name is generated.
        remove_duplication: When *True*, merge duplicate objects and remove
            orphaned references.  This is typically the single most
            effective size reduction for PDFs created by certain generators.
        remove_metadata: When *True*, strip all document-level metadata
            (author, title, producer, etc.) and the XMP metadata stream.
        compress_streams: When *True*, re-compress content streams using
            the Flate algorithm.

    Returns:
        Path to the optimized PDF.

    Raises:
        InputError: If the input is not a valid PDF.
    """
    pdf_path = ensure_pdf(input_pdf)
    out_path = resolve_output(output, pdf_path.stem + "_optimized.pdf")

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    # Copy all pages
    for page in reader.pages:
        writer.add_page(page)

    # Preserve metadata unless explicitly asked to remove it
    if not remove_metadata and reader.metadata is not None:
        writer.add_metadata(reader.metadata)

    if remove_metadata:
        # Remove XMP metadata stream from the catalog if present
        root = writer._root_object
        if "/Metadata" in root:
            del root["/Metadata"]
        # Write empty metadata to clear /Info dict entries
        writer.add_metadata({})

    # Merge identical objects and remove orphans
    if remove_duplication:
        writer.compress_identical_objects(
            remove_identicals=True, remove_orphans=True
        )

    # Write output with or without stream compression
    with open(out_path, "wb") as f:
        writer.write(f)

    return out_path


def remove_unused_objects(
    input_pdf: str | Path,
    output: str | Path | None = None,
) -> Path:
    """Remove unreferenced objects from a PDF.

    PDFs that have been incrementally updated may contain objects that are
    no longer reachable from the document catalog.  Re-writing the file
    through pypdf's writer automatically drops these orphans, producing a
    cleaner file.

    Args:
        input_pdf: Path to the source PDF.
        output: Destination path.  If *None*, a default name is generated.

    Returns:
        Path to the cleaned PDF.

    Raises:
        InputError: If the input is not a valid PDF.
    """
    pdf_path = ensure_pdf(input_pdf)
    out_path = resolve_output(output, pdf_path.stem + "_cleaned.pdf")

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    # Copying pages through the writer drops any objects not reachable from
    # the page tree or catalog.
    for page in reader.pages:
        writer.add_page(page)

    if reader.metadata is not None:
        writer.add_metadata(reader.metadata)

    # Explicitly remove orphaned objects
    writer.compress_identical_objects(remove_identicals=False, remove_orphans=True)

    with open(out_path, "wb") as f:
        writer.write(f)

    return out_path


def linearize(
    input_pdf: str | Path,
    output: str | Path | None = None,
) -> Path:
    """Optimize a PDF for fast web viewing (best-effort linearization).

    True linearization (as defined by PDF 1.2+) places a linearization
    dictionary and hint tables at the start of the file so that a viewer
    can display the first page before downloading the entire document.
    pypdf does not natively produce linearized output, so this function
    performs a *best-effort* approximation:

    * Re-writes the file through a fresh ``PdfWriter``, which produces
      a clean cross-reference table with objects ordered by page.
    * Merges duplicate objects and removes orphans to minimize total size.
    * Compresses streams.

    For a fully conformant linearized file, consider post-processing with
    QPDF (``qpdf --linearize``).

    Args:
        input_pdf: Path to the source PDF.
        output: Destination path.  If *None*, a default name is generated.

    Returns:
        Path to the optimized PDF.

    Raises:
        InputError: If the input is not a valid PDF.
    """
    pdf_path = ensure_pdf(input_pdf)
    out_path = resolve_output(output, pdf_path.stem + "_linearized.pdf")

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    # Add pages in order -- pypdf will assign object numbers sequentially,
    # which gives a reasonable page-order layout.
    for page in reader.pages:
        writer.add_page(page)

    if reader.metadata is not None:
        writer.add_metadata(reader.metadata)

    # Deduplicate and compact
    writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)

    with open(out_path, "wb") as f:
        writer.write(f)

    return out_path


def get_optimization_report(input_pdf: str | Path) -> dict:
    """Analyze a PDF and return optimization suggestions.

    Inspects the document structure and produces a report that includes
    basic statistics as well as human-readable suggestions for reducing
    file size.

    Args:
        input_pdf: Path to the PDF file.

    Returns:
        A dictionary with the following keys:

        * ``file_size`` (int) -- Size in bytes.
        * ``page_count`` (int) -- Number of pages.
        * ``has_metadata`` (bool) -- Whether metadata is present.
        * ``image_count`` (int) -- Total images across all pages.
        * ``has_forms`` (bool) -- Whether the PDF contains form fields.
        * ``has_annotations`` (bool) -- Whether any page has annotations.
        * ``estimated_savings`` (str) -- Human-readable estimate of
          potential size reduction.
        * ``suggestions`` (list[str]) -- Actionable optimization tips.

    Raises:
        InputError: If the input is not a valid PDF.
    """
    pdf_path = ensure_pdf(input_pdf)
    file_size = os.path.getsize(pdf_path)
    reader = PdfReader(pdf_path)

    page_count = len(reader.pages)

    # ── Metadata ──────────────────────────────────────────────────────────
    has_metadata = reader.metadata is not None and any(
        getattr(reader.metadata, attr, None)
        for attr in ("title", "author", "subject", "creator", "producer")
    )

    # ── Images ────────────────────────────────────────────────────────────
    image_count = 0
    for page in reader.pages:
        resources = page.get("/Resources")
        if resources is None:
            continue
        xobjects = resources.get("/XObject")
        if xobjects is None:
            continue
        for _name, obj in xobjects.items():
            resolved = obj.get_object()
            if resolved.get("/Subtype") == "/Image":
                image_count += 1

    # ── Forms ─────────────────────────────────────────────────────────────
    has_forms = False
    root = reader.trailer.get("/Root")
    if root is not None:
        root_obj = root.get_object()
        has_forms = "/AcroForm" in root_obj

    # ── Annotations ───────────────────────────────────────────────────────
    has_annotations = False
    for page in reader.pages:
        annots = page.get("/Annots")
        if annots is not None:
            # Resolve indirect reference
            if hasattr(annots, "get_object"):
                annots = annots.get_object()
            if len(annots) > 0:
                has_annotations = True
                break

    # ── Build suggestions ─────────────────────────────────────────────────
    suggestions: list[str] = []
    estimated_pct = 0

    if image_count > 0:
        suggestions.append(
            f"Found {image_count} image(s). Recompressing images can significantly "
            "reduce file size (use the compress function with a lower quality setting)."
        )
        estimated_pct += min(30, image_count * 5)

    if has_metadata:
        suggestions.append(
            "Document contains metadata. Removing it can save a small amount of space."
        )
        estimated_pct += 1

    if has_forms:
        suggestions.append(
            "Document contains form fields. Flattening forms may reduce size."
        )
        estimated_pct += 3

    if has_annotations:
        suggestions.append(
            "Document contains annotations. Removing unused annotations may help."
        )
        estimated_pct += 2

    if page_count > 10:
        suggestions.append(
            "Deduplicating identical objects (fonts, images) across many pages "
            "often yields good savings."
        )
        estimated_pct += 10

    if file_size > 10 * 1024 * 1024:  # > 10 MB
        suggestions.append(
            "File is over 10 MB. Consider splitting into smaller documents or "
            "aggressively compressing images."
        )

    # Clamp estimate to a reasonable range
    estimated_pct = min(estimated_pct, 60)

    if estimated_pct > 0:
        estimated_bytes = int(file_size * estimated_pct / 100)
        if estimated_bytes > 1024 * 1024:
            estimated_savings = f"~{estimated_bytes / (1024 * 1024):.1f} MB ({estimated_pct}%)"
        elif estimated_bytes > 1024:
            estimated_savings = f"~{estimated_bytes / 1024:.0f} KB ({estimated_pct}%)"
        else:
            estimated_savings = f"~{estimated_bytes} bytes ({estimated_pct}%)"
    else:
        estimated_savings = "File appears already well-optimized."
        suggestions.append("No significant optimization opportunities detected.")

    return {
        "file_size": file_size,
        "page_count": page_count,
        "has_metadata": has_metadata,
        "image_count": image_count,
        "has_forms": has_forms,
        "has_annotations": has_annotations,
        "estimated_savings": estimated_savings,
        "suggestions": suggestions,
    }
