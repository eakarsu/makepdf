"""PDF file attachment features using pypdf.

Provides functions to embed, extract, list, and remove file attachments
in PDF documents, similar to Adobe Acrobat's attachments panel.
"""

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    EncodedStreamObject,
    NameObject,
)

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf, output_path


def add_attachment(
    input_pdf: str | Path,
    file_path: str | Path,
    output: str | Path | None = None,
    description: str = "",
) -> Path:
    """Embed a file attachment into a PDF document.

    The file is embedded directly inside the PDF so that recipients can
    open or save the attachment from within their PDF viewer.

    Args:
        input_pdf: Path to the source PDF file.
        file_path: Path to the file to attach.
        output: Path for the output PDF. If None, defaults to
            ``<input_stem>_attached.pdf``.
        description: Optional human-readable description of the attachment.

    Returns:
        Path to the output PDF containing the embedded attachment.

    Raises:
        InputError: If the input PDF or attachment file does not exist or
            is invalid.
    """
    pdf_path = ensure_pdf(input_pdf)
    attach_path = Path(file_path)
    if not attach_path.exists():
        raise InputError(f"Attachment file not found: {attach_path}")

    out = output_path(output, f"{pdf_path.stem}_attached.pdf")

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    if reader.metadata:
        writer.add_metadata(reader.metadata)

    # Read the file content and embed it
    file_data = attach_path.read_bytes()
    writer.add_attachment(attach_path.name, file_data)

    with open(out, "wb") as f:
        writer.write(f)

    return out


def _collect_filespec_objects(reader: PdfReader) -> list:
    """Gather all file-specification objects from the PDF catalog.

    Checks both the /Names -> /EmbeddedFiles -> /Names array and the
    /Root -> /AF (associated files) array, which are the two standard
    locations for embedded file attachments.

    Args:
        reader: An open PdfReader instance.

    Returns:
        A list of resolved file-specification dictionary objects.
    """
    filespecs: list = []
    catalog = reader.trailer["/Root"]

    # Method 1: /Names -> /EmbeddedFiles -> /Names array
    if "/Names" in catalog:
        names_dict = catalog["/Names"]
        if "/EmbeddedFiles" in names_dict:
            embedded_files = names_dict["/EmbeddedFiles"]
            if "/Names" in embedded_files:
                names_array = embedded_files["/Names"]
                # The names array alternates: [name1, filespec1, name2, filespec2, ...]
                for i in range(1, len(names_array), 2):
                    filespec = names_array[i]
                    filespec = filespec.get_object() if hasattr(filespec, "get_object") else filespec
                    filespecs.append(filespec)

    # Method 2: /Root -> /AF (Associated Files) array
    if "/AF" in catalog:
        af_array = catalog["/AF"]
        af_array = af_array.get_object() if hasattr(af_array, "get_object") else af_array
        for item in af_array:
            filespec = item.get_object() if hasattr(item, "get_object") else item
            if filespec not in filespecs:
                filespecs.append(filespec)

    return filespecs


def extract_attachments(
    input_pdf: str | Path,
    output_dir: str | Path,
) -> list[Path]:
    """Extract all embedded file attachments from a PDF.

    Writes each embedded file to the specified output directory, preserving
    the original file names stored in the PDF.

    Args:
        input_pdf: Path to the source PDF file.
        output_dir: Directory where extracted files will be written. Created
            automatically if it does not exist.

    Returns:
        List of Paths to the extracted files.

    Raises:
        InputError: If the input PDF does not exist, is invalid, or contains
            no embedded attachments.
    """
    pdf_path = ensure_pdf(input_pdf)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(pdf_path)
    filespecs = _collect_filespec_objects(reader)

    if not filespecs:
        raise InputError(f"No embedded attachments found in: {pdf_path}")

    extracted: list[Path] = []

    for filespec in filespecs:
        # /UF (Unicode filename) is preferred; fall back to /F
        filename = None
        if "/UF" in filespec:
            filename = str(filespec["/UF"])
        elif "/F" in filespec:
            filename = str(filespec["/F"])
        else:
            continue

        # The actual file data lives under /EF -> /F
        if "/EF" not in filespec:
            continue

        ef_dict = filespec["/EF"]
        ef_dict = ef_dict.get_object() if hasattr(ef_dict, "get_object") else ef_dict

        if "/F" not in ef_dict:
            continue

        stream = ef_dict["/F"]
        stream = stream.get_object() if hasattr(stream, "get_object") else stream

        file_data = stream.get_data()
        dest = out_dir / filename
        dest.write_bytes(file_data)
        extracted.append(dest)

    return extracted


def list_attachments(input_pdf: str | Path) -> list[dict]:
    """List all embedded file attachments in a PDF.

    Args:
        input_pdf: Path to the PDF file to inspect.

    Returns:
        A list of dicts, each containing:
            - ``name`` (str): The attachment file name.
            - ``description`` (str): The description stored in the PDF, or
              an empty string if none is set.
            - ``size`` (int): The file size in bytes.

    Raises:
        InputError: If the input PDF does not exist or is invalid.
    """
    pdf_path = ensure_pdf(input_pdf)
    reader = PdfReader(pdf_path)
    filespecs = _collect_filespec_objects(reader)

    results: list[dict] = []

    for filespec in filespecs:
        # Resolve filename
        filename = None
        if "/UF" in filespec:
            filename = str(filespec["/UF"])
        elif "/F" in filespec:
            filename = str(filespec["/F"])
        else:
            continue

        # Description
        desc = ""
        if "/Desc" in filespec:
            desc = str(filespec["/Desc"])

        # File size from the embedded stream
        size = 0
        if "/EF" in filespec:
            ef_dict = filespec["/EF"]
            ef_dict = ef_dict.get_object() if hasattr(ef_dict, "get_object") else ef_dict
            if "/F" in ef_dict:
                stream = ef_dict["/F"]
                stream = stream.get_object() if hasattr(stream, "get_object") else stream
                # Try /Params -> /Size first (stored metadata), then fall
                # back to the actual decoded data length.
                if "/Params" in stream and "/Size" in stream["/Params"]:
                    size = int(stream["/Params"]["/Size"])
                else:
                    size = len(stream.get_data())

        results.append({
            "name": filename,
            "description": desc,
            "size": size,
        })

    return results


def remove_attachments(
    input_pdf: str | Path,
    output: str | Path | None = None,
) -> Path:
    """Remove all embedded file attachments from a PDF.

    Creates a clean copy of the PDF with all embedded files stripped out
    while preserving all pages, annotations, and other content.

    Args:
        input_pdf: Path to the source PDF file.
        output: Path for the output PDF. If None, defaults to
            ``<input_stem>_no_attachments.pdf``.

    Returns:
        Path to the output PDF with attachments removed.

    Raises:
        InputError: If the input PDF does not exist or is invalid.
    """
    pdf_path = ensure_pdf(input_pdf)
    out = output_path(output, f"{pdf_path.stem}_no_attachments.pdf")

    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    if reader.metadata:
        writer.add_metadata(reader.metadata)

    # Remove /Names -> /EmbeddedFiles from the catalog
    catalog = writer._root_object
    if "/Names" in catalog:
        names_dict = catalog["/Names"]
        names_obj = names_dict.get_object() if hasattr(names_dict, "get_object") else names_dict
        if "/EmbeddedFiles" in names_obj:
            del names_obj[NameObject("/EmbeddedFiles")]
        # Remove the /Names entry entirely if it is now empty
        if len(names_obj) == 0:
            del catalog[NameObject("/Names")]

    # Remove /AF (associated files) from the catalog
    if "/AF" in catalog:
        del catalog[NameObject("/AF")]

    with open(out, "wb") as f:
        writer.write(f)

    return out
