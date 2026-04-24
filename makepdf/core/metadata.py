"""PDF metadata reading and editing using pypdf.

Provides functionality similar to Adobe Acrobat's *Document Properties*
dialog: read, set, and remove standard PDF metadata fields (Title, Author,
Subject, Keywords, Creator, Producer, dates) as well as custom XMP or
Info-dictionary entries.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf, output_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_STANDARD_KEYS = {
    "/Title": "title",
    "/Author": "author",
    "/Subject": "subject",
    "/Keywords": "keywords",
    "/Creator": "creator",
    "/Producer": "producer",
    "/CreationDate": "creation_date",
    "/ModDate": "modification_date",
}

_REVERSE_KEYS = {v: k for k, v in _STANDARD_KEYS.items()}


def _parse_pdf_date(value: str | None) -> str | None:
    """Convert a PDF date string (e.g. ``D:20240101120000+00'00'``) to ISO 8601.

    If parsing fails the raw string is returned as-is so no data is lost.

    Args:
        value: A PDF date string, or ``None``.

    Returns:
        An ISO-8601 formatted string, the raw value, or ``None``.
    """
    if value is None:
        return None

    raw = str(value)

    # Strip the optional "D:" prefix
    cleaned = raw
    if cleaned.startswith("D:"):
        cleaned = cleaned[2:]

    # Remove timezone apostrophes: +00'00' -> +0000
    cleaned = cleaned.replace("'", "")

    # Try common PDF date formats
    for fmt in (
        "%Y%m%d%H%M%S%z",
        "%Y%m%d%H%M%S",
        "%Y%m%d%H%M",
        "%Y%m%d",
        "%Y",
    ):
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.isoformat()
        except ValueError:
            continue

    # Return the raw value if we cannot parse it
    return raw


def _format_pdf_date(value: str | datetime) -> str:
    """Convert a datetime or ISO string to a PDF date string.

    Args:
        value: A ``datetime`` object or an ISO-8601 string.

    Returns:
        A PDF date string like ``D:20240101120000+00'00'``.
    """
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            # If it already looks like a PDF date, pass it through
            return value

    return value.strftime("D:%Y%m%d%H%M%S")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_metadata(input_pdf: str | Path) -> dict[str, Any]:
    """Extract all metadata from a PDF file.

    Reads both the standard Info dictionary fields and any additional
    (custom) entries.

    Args:
        input_pdf: Path to the PDF file.

    Returns:
        A dictionary with the following keys:

        - **title** (``str | None``): Document title.
        - **author** (``str | None``): Document author.
        - **subject** (``str | None``): Document subject / description.
        - **keywords** (``str | None``): Comma-separated keywords.
        - **creator** (``str | None``): Application that created the content.
        - **producer** (``str | None``): PDF library that produced the file.
        - **creation_date** (``str | None``): ISO-8601 creation timestamp.
        - **modification_date** (``str | None``): ISO-8601 last-modified timestamp.
        - **custom** (``dict``): Any non-standard Info dictionary entries.

    Raises:
        InputError: If the input file does not exist or is not a PDF.
    """
    pdf_path = ensure_pdf(input_pdf)

    try:
        reader = PdfReader(pdf_path)
        meta = reader.metadata

        result: dict[str, Any] = {
            "title": None,
            "author": None,
            "subject": None,
            "keywords": None,
            "creator": None,
            "producer": None,
            "creation_date": None,
            "modification_date": None,
            "custom": {},
        }

        if meta is None:
            return result

        # Extract standard fields
        for pdf_key, dict_key in _STANDARD_KEYS.items():
            raw_value = meta.get(pdf_key)
            if raw_value is None:
                continue

            if dict_key in ("creation_date", "modification_date"):
                result[dict_key] = _parse_pdf_date(str(raw_value))
            else:
                result[dict_key] = str(raw_value)

        # Collect custom (non-standard) fields
        standard_pdf_keys = set(_STANDARD_KEYS.keys())
        for key in meta:
            if key not in standard_pdf_keys:
                result["custom"][key.lstrip("/")] = str(meta[key])

        return result

    except InputError:
        raise
    except Exception as exc:
        raise InputError(f"Failed to read PDF metadata: {exc}") from exc


def set_metadata(
    input_pdf: str | Path,
    output: str | Path | None = None,
    *,
    title: str | None = None,
    author: str | None = None,
    subject: str | None = None,
    keywords: str | None = None,
    creator: str | None = None,
    producer: str | None = None,
    custom: dict[str, str] | None = None,
) -> Path:
    """Set metadata fields on a PDF.

    Only the fields that are explicitly provided (non-``None``) will be
    updated; all other existing metadata is preserved.

    Args:
        input_pdf: Path to the source PDF.
        output: Optional destination path.  When ``None`` the output file
            is written as ``<stem>_metadata.pdf`` in the current directory.
        title: Document title.
        author: Document author.
        subject: Document subject / description.
        keywords: Comma-separated keywords string.
        creator: Application that created the original content.
        producer: PDF library / tool that produced the file.
        custom: A dictionary of additional metadata entries to set.
            Keys should be plain names (without the leading ``/``).

    Returns:
        Path to the PDF with updated metadata.

    Raises:
        InputError: If the input file does not exist or is not a PDF.
    """
    pdf_path = ensure_pdf(input_pdf)
    out = output_path(output, pdf_path.stem + "_metadata.pdf")

    try:
        reader = PdfReader(pdf_path)
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        # Preserve existing metadata first
        if reader.metadata:
            writer.add_metadata(reader.metadata)

        # Build the update dictionary — only include provided fields
        updates: dict[str, str] = {}

        field_map = {
            "/Title": title,
            "/Author": author,
            "/Subject": subject,
            "/Keywords": keywords,
            "/Creator": creator,
            "/Producer": producer,
        }

        for pdf_key, value in field_map.items():
            if value is not None:
                updates[pdf_key] = value

        # Add custom fields with the leading slash
        if custom:
            for key, value in custom.items():
                pdf_key = key if key.startswith("/") else f"/{key}"
                updates[pdf_key] = str(value)

        if updates:
            writer.add_metadata(updates)

        with open(out, "wb") as f:
            writer.write(f)

    except InputError:
        raise
    except Exception as exc:
        raise InputError(f"Failed to set PDF metadata: {exc}") from exc

    return out


def remove_metadata(
    input_pdf: str | Path,
    output: str | Path | None = None,
) -> Path:
    """Strip ALL metadata from a PDF.

    Removes the entire Info dictionary so the resulting PDF contains no
    title, author, dates, or any other metadata fields.  This is useful
    for privacy, redaction, or before distributing documents publicly.

    Args:
        input_pdf: Path to the source PDF.
        output: Optional destination path.  When ``None`` the output file
            is written as ``<stem>_no_metadata.pdf`` in the current
            directory.

    Returns:
        Path to the metadata-free PDF.

    Raises:
        InputError: If the input file does not exist or is not a PDF.
    """
    pdf_path = ensure_pdf(input_pdf)
    out = output_path(output, pdf_path.stem + "_no_metadata.pdf")

    try:
        reader = PdfReader(pdf_path)
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        # Write an empty metadata dictionary to clear all fields.
        # pypdf's add_metadata replaces the Info dict contents.
        writer.add_metadata(
            {
                "/Title": "",
                "/Author": "",
                "/Subject": "",
                "/Keywords": "",
                "/Creator": "",
                "/Producer": "",
            }
        )

        # Remove the Info dictionary entirely from the trailer
        # so no metadata remnants remain.
        if hasattr(writer, "_info"):
            writer._info = None
        # Also remove /Info from the root trailer if present
        try:
            trailer = getattr(writer, "_root_object", None) or getattr(writer, "trailer", None)
            if trailer and "/Info" in trailer:
                del trailer["/Info"]
        except (AttributeError, KeyError, TypeError):
            pass

        with open(out, "wb") as f:
            writer.write(f)

    except InputError:
        raise
    except Exception as exc:
        raise InputError(f"Failed to remove PDF metadata: {exc}") from exc

    return out
