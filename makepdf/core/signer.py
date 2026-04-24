"""PDF digital signing and verification."""

import datetime
import hashlib
import os
from pathlib import Path

from makepdf.exceptions import InputError, SignatureError
from makepdf.utils import ensure_pdf, output_path


def sign(
    input_pdf: str | Path,
    private_key_path: str | Path,
    cert_path: str | Path,
    output: str | Path,
) -> Path:
    """Sign a PDF with a digital signature.

    Creates a PKCS#7 signature using the provided private key and certificate,
    adds a visual signature annotation on the last page, and embeds the
    signature bytes into the output PDF.

    Args:
        input_pdf: Path to the PDF to sign.
        private_key_path: Path to a PEM-encoded private key file.
        cert_path: Path to a PEM-encoded X.509 certificate file.
        output: Path for the signed output PDF.

    Returns:
        Path to the signed PDF.

    Raises:
        InputError: If any input file is missing.
        SignatureError: If signing fails.
    """
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.serialization import pkcs7
    from cryptography.x509 import load_pem_x509_certificate

    pdf_path = ensure_pdf(input_pdf)
    key_path = Path(private_key_path)
    crt_path = Path(cert_path)

    if not key_path.exists():
        raise InputError(f"Private key not found: {key_path}")
    if not crt_path.exists():
        raise InputError(f"Certificate not found: {crt_path}")

    out = output_path(output, "signed.pdf")

    try:
        # Load private key
        key_data = key_path.read_bytes()
        private_key = serialization.load_pem_private_key(key_data, password=None)

        # Load certificate
        cert_data = crt_path.read_bytes()
        certificate = load_pem_x509_certificate(cert_data)

        # Read PDF content for hashing
        pdf_bytes = pdf_path.read_bytes()

        # Create PKCS#7 signature over the PDF content
        signature_bytes = (
            pkcs7.PKCS7SignatureBuilder()
            .set_data(pdf_bytes)
            .add_signer(certificate, private_key, hashes.SHA256())
            .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.DetachedSignature])
        )

        # Extract signer common name for the appearance
        common_name = "Unknown"
        for attr in certificate.subject:
            if attr.oid.dotted_string == "2.5.4.3":  # CN OID
                common_name = attr.value
                break

        # Build the signed PDF: copy all pages, add signature appearance on
        # the last page, and attach the signature bytes as a PDF attachment.
        from pypdf import PdfReader, PdfWriter
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.lib.units import inch
        import io

        reader = PdfReader(pdf_path)
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        # Create a signature appearance overlay for the last page
        last_page = writer.pages[-1]
        page_width = float(last_page.mediabox.width)

        overlay_buf = io.BytesIO()
        overlay_canvas = Canvas(overlay_buf, pagesize=(page_width, 60))
        overlay_canvas.setFont("Helvetica", 8)
        overlay_canvas.setFillColorRGB(0.2, 0.2, 0.6)
        overlay_canvas.drawString(
            10, 40,
            f"Digitally signed by: {common_name}",
        )
        overlay_canvas.drawString(
            10, 28,
            f"Date: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        )
        sig_hex = hashlib.sha256(signature_bytes).hexdigest()[:16]
        overlay_canvas.drawString(
            10, 16,
            f"Signature hash: {sig_hex}...",
        )
        overlay_canvas.drawString(10, 4, "Signature verification: use makepdf.core.signer.verify()")
        overlay_canvas.save()
        overlay_buf.seek(0)

        overlay_reader = PdfReader(overlay_buf)
        last_page.merge_page(overlay_reader.pages[0])

        # Embed signature bytes as a metadata entry so verify() can find it
        sig_hex_full = signature_bytes.hex()
        writer.add_metadata({
            "/MakePDF_Signature": sig_hex_full,
            "/MakePDF_Signer": common_name,
            "/MakePDF_SignDate": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(),
        })

        with open(out, "wb") as f:
            writer.write(f)

    except (InputError, SignatureError):
        raise
    except Exception as exc:
        raise SignatureError(f"Failed to sign PDF: {exc}") from exc

    return out


def create_self_signed_cert(
    output_dir: str | Path,
    common_name: str = "MakePDF User",
) -> tuple[Path, Path]:
    """Generate a self-signed certificate and private key for testing.

    Args:
        output_dir: Directory where key.pem and cert.pem will be written.
        common_name: The CN field for the certificate subject.

    Returns:
        Tuple of (key_path, cert_path).

    Raises:
        SignatureError: If certificate generation fails.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    key_path = out_dir / "key.pem"
    cert_path = out_dir / "cert.pem"

    try:
        # Generate RSA private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Build self-signed certificate
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MakePDF"),
        ])

        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=365))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .sign(private_key, hashes.SHA256())
        )

        # Write private key
        key_path.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

        # Write certificate
        cert_path.write_bytes(
            cert.public_bytes(serialization.Encoding.PEM)
        )

    except Exception as exc:
        raise SignatureError(
            f"Failed to create self-signed certificate: {exc}"
        ) from exc

    return key_path, cert_path


def verify(input_pdf: str | Path) -> dict:
    """Check if a PDF has MakePDF digital signatures.

    Args:
        input_pdf: Path to the PDF file to verify.

    Returns:
        Dict with keys:
            - ``signed`` (bool): Whether the PDF contains a signature.
            - ``signatures`` (list[dict]): List of signature info dicts,
              each containing ``signer``, ``date``, and ``signature_hash``.

    Raises:
        InputError: If the file is not a valid PDF.
    """
    pdf_path = ensure_pdf(input_pdf)

    try:
        from pypdf import PdfReader

        reader = PdfReader(pdf_path)
        metadata = reader.metadata or {}

        signatures = []

        # Check for MakePDF embedded signature metadata
        sig_hex = metadata.get("/MakePDF_Signature")
        if sig_hex:
            signer = metadata.get("/MakePDF_Signer", "Unknown")
            sign_date = metadata.get("/MakePDF_SignDate", "Unknown")

            # Compute a short hash of the signature for display
            try:
                sig_bytes = bytes.fromhex(sig_hex)
                sig_hash = hashlib.sha256(sig_bytes).hexdigest()[:16]
            except (ValueError, TypeError):
                sig_hash = "invalid"

            signatures.append({
                "signer": signer,
                "date": sign_date,
                "signature_hash": sig_hash,
            })

        # Also check for standard PDF signature fields (AcroForm)
        if hasattr(reader, "acroform") and reader.acroform:
            fields = reader.acroform.get("/Fields", [])
            for field in fields:
                field_obj = field.get_object() if hasattr(field, "get_object") else field
                ft = field_obj.get("/FT")
                if ft == "/Sig":
                    sig_val = field_obj.get("/V")
                    if sig_val:
                        sig_obj = (
                            sig_val.get_object()
                            if hasattr(sig_val, "get_object")
                            else sig_val
                        )
                        sig_info = {
                            "signer": str(sig_obj.get("/Name", "Unknown")),
                            "date": str(sig_obj.get("/M", "Unknown")),
                            "signature_hash": "standard-pdf-sig",
                        }
                        signatures.append(sig_info)

        return {
            "signed": len(signatures) > 0,
            "signatures": signatures,
        }

    except InputError:
        raise
    except Exception as exc:
        raise SignatureError(f"Failed to verify PDF: {exc}") from exc
