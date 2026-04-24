"""Convert between PDF and other formats (images, text)."""

from pathlib import Path

from makepdf.exceptions import DependencyError, InputError
from makepdf.utils import ensure_pdf, output_path
from makepdf.config import DEFAULT_DPI


def pdf_to_images(
    input_pdf: str | Path,
    output_dir: str | Path,
    format: str = "png",
    dpi: int = DEFAULT_DPI,
) -> list[Path]:
    """Convert each page of a PDF to an image file.

    Args:
        input_pdf: Path to the PDF file.
        output_dir: Directory where image files will be saved.
        format: Image format — ``"png"``, ``"jpg"``, ``"jpeg"``, ``"tiff"``,
                etc. (default ``"png"``).
        dpi: Resolution in dots per inch (default from config).

    Returns:
        List of Paths to the generated image files, one per page.

    Raises:
        DependencyError: If pdf2image is not installed.
        InputError: If the input file is invalid.
    """
    try:
        from pdf2image import convert_from_path
    except ImportError:
        raise DependencyError(
            "pdf2image is required for PDF-to-image conversion. "
            "Install it with: pip install pdf2image\n"
            "You also need poppler-utils installed on your system."
        )

    pdf_path = ensure_pdf(input_pdf)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Normalise format string
    fmt = format.lower().strip(".")
    if fmt == "jpg":
        fmt = "jpeg"

    try:
        images = convert_from_path(str(pdf_path), dpi=dpi)
    except Exception as exc:
        raise InputError(f"Failed to convert PDF to images: {exc}") from exc

    output_paths: list[Path] = []
    save_fmt = fmt.upper()
    # For file extension, use the original user-provided format
    ext = format.lower().strip(".")

    for i, image in enumerate(images, start=1):
        file_path = out_dir / f"page_{i:04d}.{ext}"
        image.save(str(file_path), save_fmt)
        output_paths.append(file_path)

    return output_paths


def images_to_pdf(
    image_paths: list[str | Path],
    output: str | Path,
    page_size: str = "A4",
) -> Path:
    """Convert a list of images to a PDF with one image per page.

    Delegates to :func:`makepdf.core.creator.from_images`.

    Args:
        image_paths: Paths to image files.
        output: Path for the output PDF.
        page_size: Page size name (default ``"A4"``).

    Returns:
        Path to the created PDF.
    """
    from makepdf.core.creator import from_images

    return from_images(image_paths, output, page_size=page_size)


def pdf_to_text(input_pdf: str | Path) -> str:
    """Extract text content from a PDF.

    Delegates to :func:`makepdf.core.text_extractor.extract_text`.

    Args:
        input_pdf: Path to the PDF file.

    Returns:
        Extracted text as a single string.
    """
    from makepdf.core.text_extractor import extract_text

    return extract_text(input_pdf)
