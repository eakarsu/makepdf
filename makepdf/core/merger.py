"""PDF merge, split, and page-manipulation operations."""

from pathlib import Path

from pypdf import PdfReader, PdfWriter

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf, output_path


def merge(pdf_paths: list[str | Path], output: str | Path | None = None) -> Path:
    """Merge multiple PDFs into a single file.

    Args:
        pdf_paths: List of paths to PDF files to merge (in order).
        output: Destination path. Defaults to ``merged.pdf``.

    Returns:
        Path to the merged PDF.
    """
    if not pdf_paths:
        raise InputError("No PDF paths provided for merging")

    out = output_path(output, "merged.pdf")
    writer = PdfWriter()

    for p in pdf_paths:
        path = ensure_pdf(p)
        reader = PdfReader(str(path))
        for page in reader.pages:
            writer.add_page(page)

    with open(out, "wb") as f:
        writer.write(f)

    return out


def split(
    input_pdf: str | Path,
    page_ranges: list[tuple[int, int]],
    output_dir: str | Path | None = None,
) -> list[Path]:
    """Split a PDF into multiple files based on page ranges.

    Args:
        input_pdf: Path to the source PDF.
        page_ranges: List of ``(start, end)`` tuples with **1-indexed**,
            inclusive page numbers.  E.g. ``[(1, 3), (4, 6)]``.
        output_dir: Directory for the output files.  Defaults to the
            current working directory.

    Returns:
        List of Paths to the created split files (``split_1.pdf``,
        ``split_2.pdf``, etc.).
    """
    path = ensure_pdf(input_pdf)
    reader = PdfReader(str(path))
    total = len(reader.pages)

    if not page_ranges:
        raise InputError("No page ranges provided for splitting")

    out_dir = Path(output_dir) if output_dir is not None else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[Path] = []

    for idx, (start, end) in enumerate(page_ranges, start=1):
        if start < 1 or end < start or end > total:
            raise InputError(
                f"Invalid page range ({start}, {end}) for PDF with {total} pages"
            )

        writer = PdfWriter()
        for page_num in range(start - 1, end):  # convert to 0-indexed
            writer.add_page(reader.pages[page_num])

        out_file = out_dir / f"split_{idx}.pdf"
        with open(out_file, "wb") as f:
            writer.write(f)
        results.append(out_file)

    return results


def extract_pages(
    input_pdf: str | Path,
    pages: list[int],
    output: str | Path | None = None,
) -> Path:
    """Extract specific pages into a new PDF.

    Args:
        input_pdf: Path to the source PDF.
        pages: List of **1-indexed** page numbers to extract.
        output: Destination path.  Defaults to ``extracted.pdf``.

    Returns:
        Path to the new PDF containing the extracted pages.
    """
    path = ensure_pdf(input_pdf)
    reader = PdfReader(str(path))
    total = len(reader.pages)
    out = output_path(output, "extracted.pdf")

    if not pages:
        raise InputError("No pages specified for extraction")

    writer = PdfWriter()
    for p in pages:
        if p < 1 or p > total:
            raise InputError(
                f"Page {p} out of range for PDF with {total} pages"
            )
        writer.add_page(reader.pages[p - 1])

    with open(out, "wb") as f:
        writer.write(f)

    return out


def interleave(
    pdf_a: str | Path,
    pdf_b: str | Path,
    output: str | Path | None = None,
) -> Path:
    """Interleave pages from two PDFs (A1, B1, A2, B2, ...).

    If one PDF is longer than the other, its remaining pages are appended
    at the end.

    Args:
        pdf_a: Path to the first PDF.
        pdf_b: Path to the second PDF.
        output: Destination path.  Defaults to ``interleaved.pdf``.

    Returns:
        Path to the interleaved PDF.
    """
    path_a = ensure_pdf(pdf_a)
    path_b = ensure_pdf(pdf_b)
    out = output_path(output, "interleaved.pdf")

    reader_a = PdfReader(str(path_a))
    reader_b = PdfReader(str(path_b))

    writer = PdfWriter()
    max_len = max(len(reader_a.pages), len(reader_b.pages))

    for i in range(max_len):
        if i < len(reader_a.pages):
            writer.add_page(reader_a.pages[i])
        if i < len(reader_b.pages):
            writer.add_page(reader_b.pages[i])

    with open(out, "wb") as f:
        writer.write(f)

    return out


def rotate_pages(
    input_pdf: str | Path,
    pages: list[int],
    angle: int,
    output: str | Path | None = None,
) -> Path:
    """Rotate specified pages by the given angle.

    Args:
        input_pdf: Path to the source PDF.
        pages: List of **1-indexed** page numbers to rotate.
        angle: Rotation angle — must be 90, 180, or 270.
        output: Destination path.  Defaults to ``rotated.pdf``.

    Returns:
        Path to the new PDF with rotated pages.
    """
    if angle not in (90, 180, 270):
        raise InputError(f"Angle must be 90, 180, or 270 — got {angle}")

    path = ensure_pdf(input_pdf)
    reader = PdfReader(str(path))
    total = len(reader.pages)
    out = output_path(output, "rotated.pdf")

    writer = PdfWriter()
    pages_set = set(pages)

    for idx, page in enumerate(reader.pages):
        page_num = idx + 1  # 1-indexed
        if page_num in pages_set:
            if page_num < 1 or page_num > total:
                raise InputError(
                    f"Page {page_num} out of range for PDF with {total} pages"
                )
            page.rotate(angle)
        writer.add_page(page)

    # Validate that all requested pages are within range
    for p in pages:
        if p < 1 or p > total:
            raise InputError(
                f"Page {p} out of range for PDF with {total} pages"
            )

    with open(out, "wb") as f:
        writer.write(f)

    return out


def reverse(
    input_pdf: str | Path,
    output: str | Path | None = None,
) -> Path:
    """Reverse page order of a PDF.

    Args:
        input_pdf: Path to the source PDF.
        output: Destination path.  Defaults to ``reversed.pdf``.

    Returns:
        Path to the reversed PDF.
    """
    path = ensure_pdf(input_pdf)
    reader = PdfReader(str(path))
    out = output_path(output, "reversed.pdf")

    writer = PdfWriter()
    for page in reversed(reader.pages):
        writer.add_page(page)

    with open(out, "wb") as f:
        writer.write(f)

    return out


def delete_pages(
    input_pdf: str | Path,
    pages: list[int],
    output: str | Path | None = None,
) -> Path:
    """Remove specified pages from a PDF.

    Args:
        input_pdf: Path to the source PDF.
        pages: List of **1-indexed** page numbers to delete.
        output: Destination path.  Defaults to ``trimmed.pdf``.

    Returns:
        Path to the new PDF with pages removed.
    """
    path = ensure_pdf(input_pdf)
    reader = PdfReader(str(path))
    total = len(reader.pages)
    out = output_path(output, "trimmed.pdf")

    if not pages:
        raise InputError("No pages specified for deletion")

    # Validate page numbers
    for p in pages:
        if p < 1 or p > total:
            raise InputError(
                f"Page {p} out of range for PDF with {total} pages"
            )

    delete_set = set(pages)

    if len(delete_set) >= total:
        raise InputError("Cannot delete all pages from the PDF")

    writer = PdfWriter()
    for idx, page in enumerate(reader.pages):
        if (idx + 1) not in delete_set:
            writer.add_page(page)

    with open(out, "wb") as f:
        writer.write(f)

    return out


def reorder_pages(
    input_pdf: str | Path,
    order: list[int],
    output: str | Path | None = None,
) -> Path:
    """Reorder pages in a PDF according to a custom sequence.

    Args:
        input_pdf: Path to the source PDF.
        order: List of **1-indexed** page numbers in the desired order.
            May include duplicates (to repeat pages) or omit pages
            (to drop them).  E.g. ``[3, 1, 2]`` puts page 3 first.
        output: Destination path.  Defaults to ``reordered.pdf``.

    Returns:
        Path to the reordered PDF.
    """
    path = ensure_pdf(input_pdf)
    reader = PdfReader(str(path))
    total = len(reader.pages)
    out = output_path(output, "reordered.pdf")

    if not order:
        raise InputError("Page order list must not be empty")

    for p in order:
        if p < 1 or p > total:
            raise InputError(
                f"Page {p} out of range for PDF with {total} pages"
            )

    writer = PdfWriter()
    for p in order:
        writer.add_page(reader.pages[p - 1])

    with open(out, "wb") as f:
        writer.write(f)

    return out
