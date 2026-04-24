"""Compress PDF files and retrieve PDF metadata."""

import io
import os
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf, output_path as resolve_output


# Quality presets: maps quality name to JPEG quality (0-100) and whether to
# aggressively remove metadata / flatten structures.
_QUALITY_PRESETS = {
    "low": {"jpeg_quality": 30, "remove_dupes": True, "compress_streams": True},
    "medium": {"jpeg_quality": 55, "remove_dupes": True, "compress_streams": True},
    "high": {"jpeg_quality": 80, "remove_dupes": True, "compress_streams": True},
}


def _recompress_image(image_obj, jpeg_quality: int):
    """Re-encode an image XObject in-place at the given JPEG quality."""
    try:
        width = int(image_obj["/Width"])
        height = int(image_obj["/Height"])
        data = image_obj.get_data()
    except Exception:
        return

    filters = image_obj.get("/Filter")
    if filters is not None:
        if isinstance(filters, list):
            filter_names = [str(f) for f in filters]
        else:
            filter_names = [str(filters)]
    else:
        filter_names = []

    # Determine colour mode
    color_space = image_obj.get("/ColorSpace")
    cs = str(color_space) if color_space else ""

    if "/DeviceRGB" in cs or "RGB" in cs:
        mode = "RGB"
    elif "/DeviceGray" in cs or "Gray" in cs:
        mode = "L"
    elif "/DeviceCMYK" in cs or "CMYK" in cs:
        mode = "CMYK"
    else:
        expected_rgb = width * height * 3
        mode = "RGB" if len(data) >= expected_rgb else "L"

    # Build a PIL Image from the data
    try:
        if "/DCTDecode" in filter_names or "/JPXDecode" in filter_names:
            img = Image.open(io.BytesIO(data))
        else:
            bits = int(image_obj.get("/BitsPerComponent", 8))
            if bits == 1:
                mode = "1"
            img = Image.frombytes(mode, (width, height), data)
    except Exception:
        return

    if img.mode == "CMYK":
        img = img.convert("RGB")
        mode = "RGB"
    if img.mode == "1":
        # 1-bit images don't benefit from JPEG compression
        return
    if img.mode not in ("RGB", "L"):
        try:
            img = img.convert("RGB")
            mode = "RGB"
        except Exception:
            return

    # Re-encode as JPEG into a bytes buffer
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
    new_data = buf.getvalue()

    # Only replace if we actually achieved a smaller size
    if len(new_data) >= len(data):
        return

    # Update the stream object
    image_obj._data = new_data
    image_obj[NameObject("/Filter")] = NameObject("/DCTDecode")
    image_obj[NameObject("/Length")] = len(new_data)
    image_obj[NameObject("/BitsPerComponent")] = 8

    if mode == "RGB":
        image_obj[NameObject("/ColorSpace")] = NameObject("/DeviceRGB")
    else:
        image_obj[NameObject("/ColorSpace")] = NameObject("/DeviceGray")

    # Remove decode-params that no longer apply
    for key in ("/DecodeParms", "/DecodeParams"):
        if key in image_obj:
            del image_obj[key]


def compress(
    input_pdf: str | Path,
    output: str | Path | None = None,
    quality: str = "medium",
) -> Path:
    """Compress a PDF file.

    Args:
        input_pdf: Path to the source PDF.
        output: Destination path. If None a default name is generated.
        quality: Compression level -- ``"low"`` (aggressive, smallest file),
                 ``"medium"`` (balanced), or ``"high"`` (minimal compression).

    Returns:
        Path to the compressed PDF.

    Raises:
        InputError: If the input is not a valid PDF or quality is unrecognised.
    """
    quality = quality.lower()
    if quality not in _QUALITY_PRESETS:
        raise InputError(
            f"Unknown quality '{quality}'. Choose from: {list(_QUALITY_PRESETS.keys())}"
        )
    preset = _QUALITY_PRESETS[quality]

    pdf_path = ensure_pdf(input_pdf)
    out_path = resolve_output(output, pdf_path.stem + "_compressed.pdf")

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    # Copy all pages
    for page in reader.pages:
        writer.add_page(page)

    # Copy metadata if present
    if reader.metadata is not None:
        writer.add_metadata(reader.metadata)

    # Remove duplicate objects to shrink the file
    if preset["remove_dupes"]:
        writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)

    # Recompress images on every page
    jpeg_quality = preset["jpeg_quality"]
    for page in writer.pages:
        resources = page.get("/Resources")
        if resources is None:
            continue
        xobjects = resources.get("/XObject")
        if xobjects is None:
            continue
        for _name, obj in xobjects.items():
            resolved = obj.get_object()
            subtype = resolved.get("/Subtype")
            if subtype == "/Image":
                _recompress_image(resolved, jpeg_quality)

    # Write output, compressing content streams
    with open(out_path, "wb") as f:
        writer.write(f)

    return out_path


def get_pdf_info(input_pdf: str | Path) -> dict:
    """Retrieve metadata and statistics about a PDF file.

    Args:
        input_pdf: Path to the PDF file.

    Returns:
        Dict with keys:
        - ``page_count`` (int)
        - ``file_size`` (int, bytes)
        - ``file_size_mb`` (float, megabytes rounded to 2 decimals)
        - ``has_images`` (bool)
        - ``has_forms`` (bool)
        - ``creator`` (str or None)
        - ``producer`` (str or None)
        - ``title`` (str or None)
        - ``author`` (str or None)
        - ``subject`` (str or None)
        - ``encrypted`` (bool)
    """
    pdf_path = ensure_pdf(input_pdf)
    file_size = os.path.getsize(pdf_path)
    reader = PdfReader(pdf_path)

    page_count = len(reader.pages)

    # Check for images
    has_images = False
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
                has_images = True
                break
        if has_images:
            break

    # Check for forms (AcroForm)
    has_forms = False
    if reader.trailer and "/Root" in reader.trailer:
        root = reader.trailer["/Root"].get_object()
        has_forms = "/AcroForm" in root

    # Metadata
    meta = reader.metadata
    creator = str(meta.creator) if meta and meta.creator else None
    producer = str(meta.producer) if meta and meta.producer else None
    title = str(meta.title) if meta and meta.title else None
    author = str(meta.author) if meta and meta.author else None
    subject = str(meta.subject) if meta and meta.subject else None

    return {
        "page_count": page_count,
        "file_size": file_size,
        "file_size_mb": round(file_size / (1024 * 1024), 2),
        "has_images": has_images,
        "has_forms": has_forms,
        "creator": creator,
        "producer": producer,
        "title": title,
        "author": author,
        "subject": subject,
        "encrypted": reader.is_encrypted,
    }
