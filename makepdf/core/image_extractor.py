"""Extract embedded images from PDF files."""

import io
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf


def _iter_page_images(page):
    """Yield (name, stream_object) tuples for all images on a PDF page."""
    resources = page.get("/Resources")
    if resources is None:
        return
    xobjects = resources.get("/XObject")
    if xobjects is None:
        return
    for name, obj in xobjects.items():
        resolved = obj.get_object()
        subtype = resolved.get("/Subtype")
        if subtype == "/Image":
            yield name, resolved


def _save_image(image_obj, output_path: Path) -> Path:
    """Decode a PDF image XObject and save it via Pillow.

    Handles the most common filter types: DCTDecode (JPEG), JPXDecode (JPEG2000),
    FlateDecode (PNG-like), and CCITTFaxDecode.
    """
    width = int(image_obj["/Width"])
    height = int(image_obj["/Height"])
    data = image_obj.get_data()
    filters = image_obj.get("/Filter")

    # Normalise filters to a list of strings
    if filters is not None:
        if isinstance(filters, list):
            filter_names = [str(f) for f in filters]
        else:
            filter_names = [str(filters)]
    else:
        filter_names = []

    # JPEG – data is already a complete JPEG stream
    if "/DCTDecode" in filter_names:
        target = output_path.with_suffix(".jpg")
        img = Image.open(io.BytesIO(data))
        img.save(target)
        return target

    # JPEG2000
    if "/JPXDecode" in filter_names:
        target = output_path.with_suffix(".jp2")
        img = Image.open(io.BytesIO(data))
        img.save(target)
        return target

    # For other filters (FlateDecode, etc.) reconstruct from raw pixel data
    color_space = image_obj.get("/ColorSpace")
    bits_per_component = int(image_obj.get("/BitsPerComponent", 8))

    # Determine PIL mode
    if color_space is not None:
        cs = str(color_space)
    else:
        cs = ""

    if "/DeviceRGB" in cs or "RGB" in cs:
        mode = "RGB"
    elif "/DeviceCMYK" in cs or "CMYK" in cs:
        mode = "CMYK"
    elif "/DeviceGray" in cs or "Gray" in cs:
        mode = "L"
    else:
        # Fallback: guess from data length
        expected_rgb = width * height * 3
        expected_gray = width * height
        if len(data) >= expected_rgb:
            mode = "RGB"
        elif len(data) >= expected_gray:
            mode = "L"
        else:
            mode = "L"

    if bits_per_component == 1:
        mode = "1"

    try:
        img = Image.frombytes(mode, (width, height), data)
    except Exception:
        # Last resort: try opening raw data as an image file
        img = Image.open(io.BytesIO(data))

    if mode == "CMYK":
        img = img.convert("RGB")

    target = output_path.with_suffix(".png")
    img.save(target)
    return target


def extract_images(
    input_pdf: str | Path,
    output_dir: str | Path,
    pages: list[int] | None = None,
) -> list[Path]:
    """Extract all embedded images from a PDF.

    Args:
        input_pdf: Path to the source PDF.
        output_dir: Directory where extracted images will be saved.
        pages: Optional list of 1-indexed page numbers. If None, all pages
               are processed.

    Returns:
        List of Paths to the saved image files.
    """
    pdf_path = ensure_pdf(input_pdf)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)

    if pages is not None:
        for p in pages:
            if p < 1 or p > total_pages:
                raise InputError(
                    f"Page {p} out of range. PDF has {total_pages} page(s)."
                )
        page_indices = [p - 1 for p in pages]
    else:
        page_indices = list(range(total_pages))

    saved: list[Path] = []
    img_counter = 0

    for idx in page_indices:
        page = reader.pages[idx]
        for _name, image_obj in _iter_page_images(page):
            img_counter += 1
            stem = f"page{idx + 1}_img{img_counter}"
            out_file = out_dir / stem  # suffix added by _save_image
            try:
                result_path = _save_image(image_obj, out_file)
                saved.append(result_path)
            except Exception:
                # Skip images that cannot be decoded
                continue

    return saved


def count_images(input_pdf: str | Path) -> dict[int, int]:
    """Count the number of embedded images on each page.

    Args:
        input_pdf: Path to the PDF file.

    Returns:
        Dict mapping 1-indexed page number to the count of images on that page.
    """
    pdf_path = ensure_pdf(input_pdf)
    reader = PdfReader(pdf_path)

    result: dict[int, int] = {}
    for i, page in enumerate(reader.pages, start=1):
        count = sum(1 for _ in _iter_page_images(page))
        result[i] = count

    return result
