"""PDF encryption and decryption using pypdf."""

from pathlib import Path

from pypdf import PdfReader, PdfWriter

from makepdf.exceptions import EncryptionError, InputError
from makepdf.utils import ensure_pdf, output_path


def encrypt(
    input_pdf: str | Path,
    output: str | Path,
    user_password: str,
    owner_password: str | None = None,
    allow_printing: bool = True,
    allow_copying: bool = True,
    allow_modifying: bool = False,
) -> Path:
    """Encrypt a PDF with passwords and permissions.

    Args:
        input_pdf: Path to the source PDF file.
        output: Path for the encrypted output PDF.
        user_password: Password required to open the PDF.
        owner_password: Password for full access. Defaults to user_password.
        allow_printing: Whether printing is permitted.
        allow_copying: Whether copying text/images is permitted.
        allow_modifying: Whether modifying the document is permitted.

    Returns:
        Path to the encrypted PDF.

    Raises:
        InputError: If input file is invalid.
        EncryptionError: If encryption fails.
    """
    pdf_path = ensure_pdf(input_pdf)
    out = output_path(output, "encrypted.pdf")

    if owner_password is None:
        owner_password = user_password

    # Build permissions flags for pypdf
    # pypdf uses individual permission keyword arguments
    permissions_flags = 0
    if allow_printing:
        permissions_flags |= 0b0000_0000_0100  # bit 3 — printing
    if allow_modifying:
        permissions_flags |= 0b0000_0000_1000  # bit 4 — modify contents
    if allow_copying:
        permissions_flags |= 0b0000_0001_0000  # bit 5 — copy/extract

    try:
        reader = PdfReader(pdf_path)
        writer = PdfWriter()

        # If the source is encrypted, try to read it unencrypted
        if reader.is_encrypted:
            raise EncryptionError(
                "Input PDF is already encrypted. Decrypt it first."
            )

        for page in reader.pages:
            writer.add_page(page)

        # Copy metadata
        if reader.metadata:
            writer.add_metadata(reader.metadata)

        writer.encrypt(
            user_password=user_password,
            owner_password=owner_password,
            permissions_flag=permissions_flags,
        )

        with open(out, "wb") as f:
            writer.write(f)

    except EncryptionError:
        raise
    except Exception as exc:
        raise EncryptionError(f"Failed to encrypt PDF: {exc}") from exc

    return out


def decrypt(
    input_pdf: str | Path,
    output: str | Path,
    password: str,
) -> Path:
    """Decrypt a password-protected PDF.

    Args:
        input_pdf: Path to the encrypted PDF file.
        output: Path for the decrypted output PDF.
        password: Password to unlock the PDF.

    Returns:
        Path to the decrypted PDF.

    Raises:
        InputError: If input file is invalid.
        EncryptionError: If the password is wrong or decryption fails.
    """
    pdf_path = ensure_pdf(input_pdf)
    out = output_path(output, "decrypted.pdf")

    try:
        reader = PdfReader(pdf_path)

        if not reader.is_encrypted:
            raise EncryptionError("PDF is not encrypted.")

        result = reader.decrypt(password)
        if result == 0:
            raise EncryptionError("Incorrect password.")

        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        # Preserve metadata
        if reader.metadata:
            writer.add_metadata(reader.metadata)

        with open(out, "wb") as f:
            writer.write(f)

    except EncryptionError:
        raise
    except Exception as exc:
        raise EncryptionError(f"Failed to decrypt PDF: {exc}") from exc

    return out


def is_encrypted(input_pdf: str | Path) -> bool:
    """Check if a PDF file is encrypted.

    Args:
        input_pdf: Path to the PDF file.

    Returns:
        True if the PDF is encrypted, False otherwise.

    Raises:
        InputError: If the file is not a valid PDF.
    """
    pdf_path = ensure_pdf(input_pdf)
    try:
        reader = PdfReader(pdf_path)
        return reader.is_encrypted
    except Exception as exc:
        raise EncryptionError(
            f"Failed to check encryption status: {exc}"
        ) from exc
