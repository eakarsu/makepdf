"""OCR processing for scanned PDF files."""

import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from makepdf.exceptions import DependencyError, InputError, OCRError
from makepdf.utils import ensure_pdf, output_path
from makepdf.config import OCR_LANGUAGE, DEFAULT_DPI


def _check_ocr_deps():
    """Verify that optional OCR dependencies are available."""
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        raise DependencyError(
            "pytesseract is required for OCR. "
            "Install it with: pip install pytesseract\n"
            "You also need Tesseract OCR installed on your system."
        )

    try:
        import pdf2image  # noqa: F401
    except ImportError:
        raise DependencyError(
            "pdf2image is required for OCR. "
            "Install it with: pip install pdf2image\n"
            "You also need poppler-utils installed on your system."
        )


def ocr_pdf(
    input_pdf: str | Path,
    output: str | Path,
    language: str = "eng",
) -> Path:
    """Convert a scanned PDF to a searchable PDF using OCR.

    Each page of the input PDF is rendered to an image, then processed
    with Tesseract to produce a searchable PDF page. The resulting pages
    are merged into a single output PDF.

    Args:
        input_pdf: Path to the scanned PDF file.
        output: Path for the searchable output PDF.
        language: Tesseract language code (default ``"eng"``).

    Returns:
        Path to the searchable PDF.

    Raises:
        DependencyError: If pytesseract or pdf2image is not installed.
        InputError: If the input file is invalid.
        OCRError: If OCR processing fails.
    """
    _check_ocr_deps()

    import pytesseract
    from pdf2image import convert_from_path

    pdf_path = ensure_pdf(input_pdf)
    out = output_path(output, "ocr_output.pdf")

    try:
        # Convert PDF pages to images
        images = convert_from_path(str(pdf_path), dpi=DEFAULT_DPI)

        if not images:
            raise OCRError("No pages found in the input PDF.")

        writer = PdfWriter()

        for i, image in enumerate(images):
            # Use pytesseract to produce a searchable PDF page from the image
            pdf_bytes = pytesseract.image_to_pdf_or_hocr(
                image,
                lang=language,
                extension="pdf",
            )

            # Read the single-page PDF produced by Tesseract and add it
            page_reader = PdfReader(io.BytesIO(pdf_bytes))
            for page in page_reader.pages:
                writer.add_page(page)

        with open(out, "wb") as f:
            writer.write(f)

    except (DependencyError, InputError, OCRError):
        raise
    except Exception as exc:
        raise OCRError(f"OCR processing failed: {exc}") from exc

    return out


def ocr_to_text(
    input_pdf: str | Path,
    language: str = "eng",
) -> str:
    """Extract text from a scanned PDF via OCR.

    Each page is converted to an image and processed with Tesseract
    to extract text content.

    Args:
        input_pdf: Path to the scanned PDF file.
        language: Tesseract language code (default ``"eng"``).

    Returns:
        Extracted text from all pages, concatenated with newlines.

    Raises:
        DependencyError: If pytesseract or pdf2image is not installed.
        InputError: If the input file is invalid.
        OCRError: If OCR processing fails.
    """
    _check_ocr_deps()

    import pytesseract
    from pdf2image import convert_from_path

    pdf_path = ensure_pdf(input_pdf)

    try:
        images = convert_from_path(str(pdf_path), dpi=DEFAULT_DPI)

        if not images:
            raise OCRError("No pages found in the input PDF.")

        text_parts: list[str] = []
        for image in images:
            text = pytesseract.image_to_string(image, lang=language)
            text_parts.append(text)

        return "\n".join(text_parts)

    except (DependencyError, InputError, OCRError):
        raise
    except Exception as exc:
        raise OCRError(f"OCR text extraction failed: {exc}") from exc
