"""Extract and search text content from PDF files."""

from pathlib import Path

from pypdf import PdfReader

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf


def extract_text(input_pdf: str | Path, pages: list[int] | None = None) -> str:
    """Extract all text from a PDF file.

    Args:
        input_pdf: Path to the PDF file.
        pages: Optional list of 1-indexed page numbers to extract from.
               If None, extract from all pages.

    Returns:
        Concatenated text content from the specified pages.

    Raises:
        InputError: If the file is not a valid PDF or page numbers are out of range.
    """
    pdf_path = ensure_pdf(input_pdf)
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)

    if pages is not None:
        for p in pages:
            if p < 1 or p > total_pages:
                raise InputError(
                    f"Page {p} out of range. PDF has {total_pages} page(s)."
                )
        selected = [reader.pages[p - 1] for p in pages]
    else:
        selected = reader.pages

    parts: list[str] = []
    for page in selected:
        text = page.extract_text() or ""
        parts.append(text)

    return "\n".join(parts)


def extract_text_by_page(input_pdf: str | Path) -> dict[int, str]:
    """Extract text from each page of a PDF, keyed by page number.

    Args:
        input_pdf: Path to the PDF file.

    Returns:
        Dict mapping 1-indexed page number to its text content.
    """
    pdf_path = ensure_pdf(input_pdf)
    reader = PdfReader(pdf_path)

    result: dict[int, str] = {}
    for i, page in enumerate(reader.pages, start=1):
        result[i] = page.extract_text() or ""

    return result


def search_text(input_pdf: str | Path, query: str) -> list[dict]:
    """Search for text occurrences within a PDF.

    Args:
        input_pdf: Path to the PDF file.
        query: The text string to search for (case-insensitive).

    Returns:
        List of dicts with keys ``page`` (1-indexed int) and ``context``
        (the full line containing the match).
    """
    if not query:
        raise InputError("Search query must not be empty.")

    pages_text = extract_text_by_page(input_pdf)
    query_lower = query.lower()
    results: list[dict] = []

    for page_num, text in pages_text.items():
        for line in text.splitlines():
            if query_lower in line.lower():
                results.append({"page": page_num, "context": line.strip()})

    return results
