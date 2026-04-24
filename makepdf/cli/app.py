"""MakePDF command-line interface built with Typer."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional

import typer

from makepdf.exceptions import MakePdfError

# ---------------------------------------------------------------------------
# App / sub-app definitions
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="makepdf",
    help="Complete PDF generation and manipulation toolkit.",
    invoke_without_command=True,
)


@app.callback()
def main(
    ctx: typer.Context,
    pdf_file: Optional[Path] = typer.Argument(None, help="PDF file to read (extracts text by default)."),
):
    """Complete PDF generation and manipulation toolkit.

    Pass a PDF file directly to open it in your default viewer:

        makepdf file.pdf
    """
    if ctx.invoked_subcommand is not None:
        return
    if pdf_file is None:
        # No file and no subcommand — show help
        typer.echo(ctx.get_help())
        raise typer.Exit(0)
    if not pdf_file.exists():
        typer.echo(f"Error: file not found: {pdf_file}", err=True)
        raise typer.Exit(1)
    if not str(pdf_file).lower().endswith(".pdf"):
        typer.echo(f"Error: not a PDF file: {pdf_file}", err=True)
        typer.echo("Use 'makepdf --help' to see available commands.", err=True)
        raise typer.Exit(1)

    import subprocess
    import platform

    pdf_path = str(pdf_file.resolve())
    system = platform.system()
    if system == "Darwin":
        subprocess.Popen(["open", pdf_path])
    elif system == "Windows":
        subprocess.Popen(["start", "", pdf_path], shell=True)
    else:
        subprocess.Popen(["xdg-open", pdf_path])

create_app = typer.Typer(name="create", help="Create PDFs from various sources.", no_args_is_help=True)
edit_app = typer.Typer(name="edit", help="Edit existing PDFs (add text, images).", no_args_is_help=True)
extract_app = typer.Typer(name="extract", help="Extract text or images from PDFs.", no_args_is_help=True)
watermark_app = typer.Typer(name="watermark", help="Add text or image watermarks.", no_args_is_help=True)
form_app = typer.Typer(name="form", help="Create, fill, and inspect PDF forms.", no_args_is_help=True)
sign_app = typer.Typer(name="sign", help="Digital signatures for PDFs.", no_args_is_help=True)
convert_app = typer.Typer(name="convert", help="Convert PDFs to/from images.", no_args_is_help=True)
toc_app = typer.Typer(name="toc", help="Table of contents / bookmark operations.", no_args_is_help=True)
ocr_app = typer.Typer(name="ocr", help="OCR operations on scanned PDFs.", no_args_is_help=True)
redact_app = typer.Typer(name="redact", help="Redact sensitive content from PDFs.", no_args_is_help=True)
crop_app = typer.Typer(name="crop", help="Crop and resize PDF pages.", no_args_is_help=True)
stamp_app = typer.Typer(name="stamp", help="Add stamps to PDFs.", no_args_is_help=True)
bates_app = typer.Typer(name="bates", help="Bates numbering for legal documents.", no_args_is_help=True)
compare_app = typer.Typer(name="compare", help="Compare two PDF documents.", no_args_is_help=True)
flatten_app = typer.Typer(name="flatten", help="Flatten PDF forms and annotations.", no_args_is_help=True)
meta_app = typer.Typer(name="metadata", help="View and edit PDF metadata.", no_args_is_help=True)
attach_app = typer.Typer(name="attach", help="Manage PDF file attachments.", no_args_is_help=True)
link_app = typer.Typer(name="link", help="Manage PDF hyperlinks.", no_args_is_help=True)
label_app = typer.Typer(name="label", help="Page label / numbering operations.", no_args_is_help=True)
opt_app = typer.Typer(name="optimize", help="Optimize PDFs for size and performance.", no_args_is_help=True)
a11y_app = typer.Typer(name="a11y", help="Accessibility tools for PDFs.", no_args_is_help=True)
markup_app = typer.Typer(name="markup", help="Text markup annotations.", no_args_is_help=True)

app.add_typer(create_app)
app.add_typer(edit_app)
app.add_typer(extract_app)
app.add_typer(watermark_app)
app.add_typer(form_app)
app.add_typer(sign_app)
app.add_typer(convert_app)
app.add_typer(toc_app)
app.add_typer(ocr_app)
app.add_typer(redact_app)
app.add_typer(crop_app)
app.add_typer(stamp_app)
app.add_typer(bates_app)
app.add_typer(compare_app)
app.add_typer(flatten_app)
app.add_typer(meta_app)
app.add_typer(attach_app)
app.add_typer(link_app)
app.add_typer(label_app)
app.add_typer(opt_app)
app.add_typer(a11y_app)
app.add_typer(markup_app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_pages(pages_str: str) -> list[int]:
    """Parse a comma-separated string of page numbers into a list of ints.

    Example: "1,3,5" -> [1, 3, 5]
    """
    parts = [p.strip() for p in pages_str.split(",") if p.strip()]
    try:
        return [int(p) for p in parts]
    except ValueError:
        typer.echo(f"Error: invalid page numbers: {pages_str}")
        raise typer.Exit(1)


def _parse_ranges(ranges_str: str) -> list[tuple[int, int]]:
    """Parse a ranges string like '1-3,4-6' into [(1,3), (4,6)]."""
    result: list[tuple[int, int]] = []
    for part in ranges_str.split(","):
        part = part.strip()
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            try:
                result.append((int(start_s.strip()), int(end_s.strip())))
            except ValueError:
                typer.echo(f"Error: invalid range: {part}")
                raise typer.Exit(1)
        else:
            try:
                n = int(part)
                result.append((n, n))
            except ValueError:
                typer.echo(f"Error: invalid range: {part}")
                raise typer.Exit(1)
    return result


def _parse_color(color_str: str) -> tuple[float, float, float]:
    """Parse 'R,G,B' string (0-1 floats or 0-255 ints) into a tuple."""
    parts = [p.strip() for p in color_str.split(",")]
    if len(parts) != 3:
        typer.echo(f"Error: color must have 3 components (R,G,B), got: {color_str}")
        raise typer.Exit(1)
    try:
        values = [float(p) for p in parts]
    except ValueError:
        typer.echo(f"Error: invalid color values: {color_str}")
        raise typer.Exit(1)
    # If any value > 1, assume 0-255 range and normalise
    if any(v > 1.0 for v in values):
        values = [v / 255.0 for v in values]
    return (values[0], values[1], values[2])


def _load_json(json_path: str) -> object:
    """Read and parse a JSON file."""
    p = Path(json_path)
    if not p.exists():
        typer.echo(f"Error: JSON file not found: {json_path}")
        raise typer.Exit(1)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        typer.echo(f"Error: invalid JSON in {json_path}: {exc}")
        raise typer.Exit(1)


def _handle_error(exc: MakePdfError) -> None:
    """Print a MakePdfError and exit with code 1."""
    typer.echo(f"Error: {exc}")
    raise typer.Exit(1)


# ===================================================================
# CREATE commands
# ===================================================================


@create_app.command("text")
def create_text(
    input: Path = typer.Argument(..., help="Path to input text file."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    font: str = typer.Option("Helvetica", "--font", help="Font family name."),
    font_size: int = typer.Option(12, "--font-size", help="Font size in points."),
    page_size: str = typer.Option("A4", "--page-size", help="Page size (A4, LETTER, etc.)."),
) -> None:
    """Create a PDF from a plain-text file."""
    from makepdf.core.creator import from_text

    if not input.exists():
        typer.echo(f"Error: file not found: {input}", err=True)
        raise typer.Exit(1)

    try:
        text = input.read_text(encoding="utf-8")
        result = from_text(text, output, font=font, font_size=font_size, page_size=page_size)
        typer.echo(f"Created PDF: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@create_app.command("html")
def create_html(
    input: Path = typer.Argument(..., help="Path to input HTML file."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    page_size: str = typer.Option("A4", "--page-size", help="Page size (A4, LETTER, etc.)."),
) -> None:
    """Create a PDF from an HTML file."""
    from makepdf.core.creator import from_html

    try:
        html_content = input.read_text(encoding="utf-8")
        result = from_html(html_content, output, page_size=page_size)
        typer.echo(f"Created PDF: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@create_app.command("markdown")
def create_markdown(
    input: Path = typer.Argument(..., help="Path to input Markdown file."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    page_size: str = typer.Option("A4", "--page-size", help="Page size (A4, LETTER, etc.)."),
) -> None:
    """Create a PDF from a Markdown file."""
    from makepdf.core.creator import from_markdown

    try:
        md_content = input.read_text(encoding="utf-8")
        result = from_markdown(md_content, output, page_size=page_size)
        typer.echo(f"Created PDF: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@create_app.command("images")
def create_images(
    images: List[Path] = typer.Argument(..., help="One or more image file paths."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    page_size: str = typer.Option("A4", "--page-size", help="Page size (A4, LETTER, etc.)."),
) -> None:
    """Create a PDF from one or more images (one image per page)."""
    from makepdf.core.creator import from_images

    try:
        result = from_images([str(p) for p in images], output, page_size=page_size)
        typer.echo(f"Created PDF: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# EDIT commands
# ===================================================================


@edit_app.command("add-text")
def edit_add_text(
    input: Path = typer.Argument(..., help="Path to input PDF."),
    page: int = typer.Option(..., "--page", help="Page number (0-based)."),
    x: float = typer.Option(..., "--x", help="X position in points."),
    y: float = typer.Option(..., "--y", help="Y position in points."),
    text: str = typer.Option(..., "--text", help="Text to add."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    font: str = typer.Option("Helvetica", "--font", help="Font family name."),
    font_size: float = typer.Option(12, "--font-size", help="Font size in points."),
    color: str = typer.Option("0,0,0", "--color", help="Text color as R,G,B (0-1 or 0-255)."),
) -> None:
    """Add text at a specific position on a page of an existing PDF."""
    from makepdf.core.editor import add_text

    try:
        rgb = _parse_color(color)
        result = add_text(
            input_pdf=str(input),
            page_num=page,
            x=x,
            y=y,
            text=text,
            output=str(output),
            font=font,
            font_size=font_size,
            color=rgb,
        )
        typer.echo(f"Edited PDF saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@edit_app.command("add-image")
def edit_add_image(
    input: Path = typer.Argument(..., help="Path to input PDF."),
    page: int = typer.Option(..., "--page", help="Page number (0-based)."),
    x: float = typer.Option(..., "--x", help="X position in points."),
    y: float = typer.Option(..., "--y", help="Y position in points."),
    image: Path = typer.Option(..., "--image", help="Path to the image file to add."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    width: Optional[float] = typer.Option(None, "--width", help="Image width in points."),
    height: Optional[float] = typer.Option(None, "--height", help="Image height in points."),
) -> None:
    """Add an image at a specific position on a page of an existing PDF."""
    from makepdf.core.editor import add_image

    try:
        result = add_image(
            input_pdf=str(input),
            page_num=page,
            x=x,
            y=y,
            image_path=str(image),
            output=str(output),
            width=width,
            height=height,
        )
        typer.echo(f"Edited PDF saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# MERGE / SPLIT / PAGE-MANIPULATION commands
# ===================================================================


@app.command("merge")
def merge_cmd(
    files: List[Path] = typer.Argument(..., help="PDF files to merge."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Merge multiple PDF files into one."""
    from makepdf.core.merger import merge

    try:
        result = merge([str(p) for p in files], output=str(output))
        typer.echo(f"Merged PDF: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@app.command("split")
def split_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF."),
    ranges: str = typer.Option(..., "--ranges", help='Page ranges, e.g. "1-3,4-6".'),
    output: Path = typer.Option(..., "-o", "--output", help="Output directory."),
) -> None:
    """Split a PDF into multiple files by page ranges."""
    from makepdf.core.merger import split

    try:
        page_ranges = _parse_ranges(ranges)
        results = split(str(input), page_ranges=page_ranges, output_dir=str(output))
        for p in results:
            typer.echo(f"  {p}")
        typer.echo(f"Split into {len(results)} file(s) in {output}")
    except MakePdfError as exc:
        _handle_error(exc)


@app.command("extract-pages")
def extract_pages_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF."),
    pages: str = typer.Option(..., "--pages", help='Comma-separated page numbers, e.g. "1,3,5".'),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Extract specific pages into a new PDF."""
    from makepdf.core.merger import extract_pages

    try:
        page_list = _parse_pages(pages)
        result = extract_pages(str(input), pages=page_list, output=str(output))
        typer.echo(f"Extracted pages to: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@app.command("rotate")
def rotate_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF."),
    pages: str = typer.Option(..., "--pages", help='Comma-separated page numbers, e.g. "1,3".'),
    angle: int = typer.Option(..., "--angle", help="Rotation angle (90, 180, or 270)."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Rotate specified pages of a PDF."""
    from makepdf.core.merger import rotate_pages

    try:
        page_list = _parse_pages(pages)
        result = rotate_pages(str(input), pages=page_list, angle=angle, output=str(output))
        typer.echo(f"Rotated PDF saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@app.command("reverse")
def reverse_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Reverse the page order of a PDF."""
    from makepdf.core.merger import reverse

    try:
        result = reverse(str(input), output=str(output))
        typer.echo(f"Reversed PDF saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@app.command("delete-pages")
def delete_pages_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF."),
    pages: str = typer.Option(..., "--pages", help='Comma-separated page numbers to delete, e.g. "2,4".'),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Delete specified pages from a PDF."""
    from makepdf.core.merger import delete_pages

    try:
        page_list = _parse_pages(pages)
        result = delete_pages(str(input), pages=page_list, output=str(output))
        typer.echo(f"Pages deleted. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# EXTRACT commands
# ===================================================================


@extract_app.command("text")
def extract_text_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF."),
    pages: Optional[str] = typer.Option(None, "--pages", help='Comma-separated page numbers, e.g. "1,3".'),
) -> None:
    """Extract text content from a PDF and print it to stdout."""
    from makepdf.core.text_extractor import extract_text

    try:
        page_list = _parse_pages(pages) if pages else None
        text = extract_text(str(input), pages=page_list)
        typer.echo(text)
    except MakePdfError as exc:
        _handle_error(exc)


@extract_app.command("images")
def extract_images_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF."),
    output: Path = typer.Option(..., "-o", "--output", help="Output directory for extracted images."),
) -> None:
    """Extract all embedded images from a PDF."""
    from makepdf.core.image_extractor import extract_images

    try:
        results = extract_images(str(input), output_dir=str(output))
        if results:
            for p in results:
                typer.echo(f"  {p}")
            typer.echo(f"Extracted {len(results)} image(s) to {output}")
        else:
            typer.echo("No images found in the PDF.")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# WATERMARK commands
# ===================================================================


@watermark_app.command("text")
def watermark_text_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF."),
    text: str = typer.Option(..., "--text", help="Watermark text."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    opacity: float = typer.Option(0.3, "--opacity", help="Watermark opacity (0.0-1.0)."),
    angle: float = typer.Option(45, "--angle", help="Rotation angle in degrees."),
    font_size: int = typer.Option(60, "--font-size", help="Font size in points."),
) -> None:
    """Add a diagonal text watermark on every page."""
    from makepdf.core.watermark import add_text_watermark

    try:
        result = add_text_watermark(
            str(input), text, output=str(output),
            opacity=opacity, angle=angle, font_size=font_size,
        )
        typer.echo(f"Watermarked PDF saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@watermark_app.command("image")
def watermark_image_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF."),
    image: Path = typer.Option(..., "--image", help="Path to watermark image."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    opacity: float = typer.Option(0.3, "--opacity", help="Watermark opacity (0.0-1.0)."),
    position: str = typer.Option("center", "--position", help="Position: center, top-left, top-right, bottom-left, bottom-right."),
    scale: float = typer.Option(0.5, "--scale", help="Scale relative to page size (0.0-1.0)."),
) -> None:
    """Add an image watermark on every page."""
    from makepdf.core.watermark import add_image_watermark

    try:
        result = add_image_watermark(
            str(input), str(image), output=str(output),
            opacity=opacity, position=position, scale=scale,
        )
        typer.echo(f"Watermarked PDF saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# HEADERS / FOOTERS
# ===================================================================


@app.command("headers")
def headers_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    header_left: str = typer.Option("", "--header-left", help="Left header text."),
    header_center: str = typer.Option("", "--header-center", help="Center header text."),
    header_right: str = typer.Option("", "--header-right", help="Right header text."),
    footer_left: str = typer.Option("", "--footer-left", help="Left footer text."),
    footer_center: str = typer.Option("", "--footer-center", help="Center footer text."),
    footer_right: str = typer.Option("", "--footer-right", help="Right footer text."),
) -> None:
    """Add headers and footers to every page. Supports {page} and {total} placeholders."""
    from makepdf.core.headers_footers import add_headers_footers

    try:
        result = add_headers_footers(
            str(input), output=str(output),
            header_left=header_left, header_center=header_center, header_right=header_right,
            footer_left=footer_left, footer_center=footer_center, footer_right=footer_right,
        )
        typer.echo(f"Headers/footers added: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# COMPRESS
# ===================================================================


@app.command("compress")
def compress_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    quality: str = typer.Option("medium", "--quality", help="Compression quality: low, medium, or high."),
) -> None:
    """Compress a PDF to reduce file size."""
    from pypdf import PdfReader, PdfWriter
    from makepdf.utils import ensure_pdf, output_path as _output_path

    valid_qualities = {"low", "medium", "high"}
    if quality not in valid_qualities:
        typer.echo(f"Error: quality must be one of {sorted(valid_qualities)}, got: {quality}")
        raise typer.Exit(1)

    try:
        src = ensure_pdf(str(input))
        out = _output_path(str(output), "compressed.pdf")

        reader = PdfReader(str(src))
        writer = PdfWriter()

        for page in reader.pages:
            page.compress_content_streams()
            writer.add_page(page)

        # Copy metadata
        if reader.metadata:
            writer.add_metadata(reader.metadata)

        with open(out, "wb") as f:
            writer.write(f)

        original_size = src.stat().st_size
        compressed_size = out.stat().st_size
        reduction = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0

        typer.echo(f"Compressed PDF saved: {out}")
        typer.echo(f"  Original:   {original_size:,} bytes")
        typer.echo(f"  Compressed: {compressed_size:,} bytes")
        typer.echo(f"  Reduction:  {reduction:.1f}%")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# INFO
# ===================================================================


@app.command("info")
def info_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF."),
) -> None:
    """Display metadata and page information about a PDF."""
    from pypdf import PdfReader
    from makepdf.utils import ensure_pdf

    try:
        src = ensure_pdf(str(input))
        reader = PdfReader(str(src))

        typer.echo(f"File: {src}")
        typer.echo(f"Pages: {len(reader.pages)}")
        typer.echo(f"Encrypted: {reader.is_encrypted}")

        meta = reader.metadata
        if meta:
            if meta.title:
                typer.echo(f"Title: {meta.title}")
            if meta.author:
                typer.echo(f"Author: {meta.author}")
            if meta.subject:
                typer.echo(f"Subject: {meta.subject}")
            if meta.creator:
                typer.echo(f"Creator: {meta.creator}")
            if meta.producer:
                typer.echo(f"Producer: {meta.producer}")
            if meta.creation_date:
                typer.echo(f"Created: {meta.creation_date}")
            if meta.modification_date:
                typer.echo(f"Modified: {meta.modification_date}")

        # Show page sizes
        for i, page in enumerate(reader.pages, 1):
            box = page.mediabox
            w = float(box.width)
            h = float(box.height)
            typer.echo(f"  Page {i}: {w:.1f} x {h:.1f} pts")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# ENCRYPT / DECRYPT
# ===================================================================


@app.command("encrypt")
def encrypt_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    password: str = typer.Option(..., "--password", help="User password for opening the PDF."),
    owner_password: Optional[str] = typer.Option(None, "--owner-password", help="Owner password for full access."),
    no_printing: bool = typer.Option(False, "--no-printing", help="Disallow printing."),
    no_copying: bool = typer.Option(False, "--no-copying", help="Disallow copying text/images."),
) -> None:
    """Encrypt a PDF with password protection."""
    from makepdf.core.encryption import encrypt

    try:
        result = encrypt(
            str(input), str(output),
            user_password=password,
            owner_password=owner_password,
            allow_printing=not no_printing,
            allow_copying=not no_copying,
        )
        typer.echo(f"Encrypted PDF saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@app.command("decrypt")
def decrypt_cmd(
    input: Path = typer.Argument(..., help="Path to encrypted PDF."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    password: str = typer.Option(..., "--password", help="Password to unlock the PDF."),
) -> None:
    """Decrypt a password-protected PDF."""
    from makepdf.core.encryption import decrypt

    try:
        result = decrypt(str(input), str(output), password=password)
        typer.echo(f"Decrypted PDF saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# FORM commands
# ===================================================================


@form_app.command("create")
def form_create_cmd(
    fields: str = typer.Option(..., "--fields", help="Path to a JSON file defining form fields."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Create a PDF with fillable form fields from a JSON definition."""
    from makepdf.core.forms import create_form

    try:
        fields_data = _load_json(fields)
        if not isinstance(fields_data, list):
            typer.echo("Error: fields JSON must be a list of field definitions.")
            raise typer.Exit(1)
        result = create_form(fields_data, output=str(output))
        typer.echo(f"Form PDF created: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@form_app.command("fill")
def form_fill_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF with form fields."),
    data: str = typer.Option(..., "--data", help="Path to a JSON file with field name/value pairs."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Fill form fields in a PDF with values from a JSON file."""
    from makepdf.core.forms import fill_form

    try:
        data_dict = _load_json(data)
        if not isinstance(data_dict, dict):
            typer.echo("Error: data JSON must be a dict of field name -> value.")
            raise typer.Exit(1)
        result = fill_form(str(input), data=data_dict, output=str(output))
        typer.echo(f"Filled form saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@form_app.command("extract")
def form_extract_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF with form fields."),
) -> None:
    """Extract form field values from a PDF and print as JSON."""
    from makepdf.core.forms import extract_form_data

    try:
        data = extract_form_data(str(input))
        typer.echo(json.dumps(data, indent=2))
    except MakePdfError as exc:
        _handle_error(exc)


@form_app.command("list-fields")
def form_list_fields_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF with form fields."),
) -> None:
    """List all form field names, types, and current values."""
    from makepdf.core.forms import list_form_fields

    try:
        fields = list_form_fields(str(input))
        if not fields:
            typer.echo("No form fields found.")
        else:
            typer.echo(json.dumps(fields, indent=2))
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# OCR commands
# ===================================================================


@ocr_app.command(name="process", hidden=False)
def ocr_process_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF (scanned)."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path with OCR text layer."),
    language: str = typer.Option("eng", "--language", help="OCR language code (e.g. eng, deu, fra)."),
) -> None:
    """Run OCR on a scanned PDF and produce a searchable PDF."""
    try:
        import ocrmypdf
    except ImportError:
        typer.echo("Error: ocrmypdf is required for OCR. Install with: pip install ocrmypdf")
        raise typer.Exit(1)

    try:
        ocrmypdf.ocr(str(input), str(output), language=language, skip_text=True)
        typer.echo(f"OCR complete. Searchable PDF saved: {output}")
    except Exception as exc:
        typer.echo(f"Error: OCR failed: {exc}")
        raise typer.Exit(1)


@ocr_app.command("text")
def ocr_text_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF (scanned)."),
    language: str = typer.Option("eng", "--language", help="OCR language code (e.g. eng, deu, fra)."),
) -> None:
    """Run OCR on a scanned PDF and print extracted text to stdout."""
    import tempfile

    try:
        import ocrmypdf
    except ImportError:
        typer.echo("Error: ocrmypdf is required for OCR. Install with: pip install ocrmypdf")
        raise typer.Exit(1)

    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name

        ocrmypdf.ocr(str(input), tmp_path, language=language, skip_text=True)

        from makepdf.core.text_extractor import extract_text
        text = extract_text(tmp_path)
        typer.echo(text)

        Path(tmp_path).unlink(missing_ok=True)
    except Exception as exc:
        typer.echo(f"Error: OCR failed: {exc}")
        raise typer.Exit(1)


# ===================================================================
# SIGN commands
# ===================================================================


@sign_app.command(name="pdf")
def sign_pdf_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF."),
    key: Path = typer.Option(..., "--key", help="Path to PEM private key file."),
    cert: Path = typer.Option(..., "--cert", help="Path to PEM certificate file."),
    output: Path = typer.Option(..., "-o", "--output", help="Output signed PDF path."),
) -> None:
    """Digitally sign a PDF with a private key and certificate."""
    try:
        from pyhanko.sign import signers, fields as sig_fields
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    except ImportError:
        typer.echo("Error: pyhanko is required for signing. Install with: pip install pyHanko[opentype]")
        raise typer.Exit(1)

    try:
        signer = signers.SimpleSigner.load(
            str(key), str(cert),
        )
        with open(str(input), "rb") as inf:
            w = IncrementalPdfFileWriter(inf)
            out_data = signers.sign_pdf(
                w,
                signers.PdfSignatureMetadata(field_name="Signature1"),
                signer=signer,
            )
        with open(str(output), "wb") as outf:
            outf.write(out_data.getvalue())

        typer.echo(f"Signed PDF saved: {output}")
    except MakePdfError as exc:
        _handle_error(exc)
    except Exception as exc:
        typer.echo(f"Error: signing failed: {exc}")
        raise typer.Exit(1)


@sign_app.command("create-cert")
def sign_create_cert_cmd(
    output: Path = typer.Option(..., "-o", "--output", help="Output directory for key and cert files."),
    name: str = typer.Option("MakePDF Self-Signed", "--name", help="Common name for the certificate."),
) -> None:
    """Generate a self-signed certificate and private key for testing."""
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime
    except ImportError:
        typer.echo("Error: cryptography is required. Install with: pip install cryptography")
        raise typer.Exit(1)

    try:
        output.mkdir(parents=True, exist_ok=True)

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, name),
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
            .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
            .sign(key, hashes.SHA256())
        )

        key_path = output / "key.pem"
        cert_path = output / "cert.pem"

        key_path.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

        typer.echo(f"Private key: {key_path}")
        typer.echo(f"Certificate: {cert_path}")
    except Exception as exc:
        typer.echo(f"Error: certificate generation failed: {exc}")
        raise typer.Exit(1)


@sign_app.command("verify")
def sign_verify_cmd(
    input: Path = typer.Argument(..., help="Path to signed PDF."),
) -> None:
    """Verify the digital signature(s) of a PDF."""
    try:
        from pyhanko.sign.validation import validate_pdf_signature
        from pyhanko.pdf_utils.reader import PdfFileReader
    except ImportError:
        typer.echo("Error: pyhanko is required for verification. Install with: pip install pyHanko[opentype]")
        raise typer.Exit(1)

    try:
        with open(str(input), "rb") as f:
            reader = PdfFileReader(f)
            sig_fields_found = reader.embedded_signatures

            if not sig_fields_found:
                typer.echo("No digital signatures found in this PDF.")
                raise typer.Exit(1)

            for sig in sig_fields_found:
                status = validate_pdf_signature(sig)
                typer.echo(f"Signature: {sig.field_name}")
                typer.echo(f"  Intact:    {status.intact}")
                typer.echo(f"  Valid:     {status.valid}")
                typer.echo(f"  Trusted:   {status.trusted}")
    except MakePdfError as exc:
        _handle_error(exc)
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(f"Error: verification failed: {exc}")
        raise typer.Exit(1)


# ===================================================================
# CONVERT commands
# ===================================================================


@convert_app.command("to-images")
def convert_to_images_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF."),
    output: Path = typer.Option(..., "-o", "--output", help="Output directory for images."),
    format: str = typer.Option("png", "--format", help="Image format: png or jpg."),
    dpi: int = typer.Option(200, "--dpi", help="Resolution in DPI."),
) -> None:
    """Convert each page of a PDF to an image file."""
    try:
        from pdf2image import convert_from_path
    except ImportError:
        typer.echo("Error: pdf2image is required. Install with: pip install pdf2image")
        raise typer.Exit(1)

    valid_formats = {"png", "jpg", "jpeg"}
    if format.lower() not in valid_formats:
        typer.echo(f"Error: format must be png or jpg, got: {format}")
        raise typer.Exit(1)

    fmt = "JPEG" if format.lower() in ("jpg", "jpeg") else "PNG"
    suffix = ".jpg" if fmt == "JPEG" else ".png"

    try:
        from makepdf.utils import ensure_pdf
        src = ensure_pdf(str(input))
        output.mkdir(parents=True, exist_ok=True)

        images = convert_from_path(str(src), dpi=dpi)
        saved: list[Path] = []
        for i, img in enumerate(images, 1):
            out_file = output / f"page_{i}{suffix}"
            img.save(str(out_file), fmt)
            saved.append(out_file)
            typer.echo(f"  {out_file}")

        typer.echo(f"Converted {len(saved)} page(s) to images in {output}")
    except MakePdfError as exc:
        _handle_error(exc)
    except Exception as exc:
        typer.echo(f"Error: conversion failed: {exc}")
        raise typer.Exit(1)


@convert_app.command("from-images")
def convert_from_images_cmd(
    images: List[Path] = typer.Argument(..., help="One or more image file paths."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Create a PDF from one or more image files."""
    from makepdf.core.creator import from_images

    try:
        result = from_images([str(p) for p in images], output=str(output))
        typer.echo(f"Created PDF from images: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# TOC commands
# ===================================================================


@toc_app.command("generate")
def toc_generate_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF."),
    entries: str = typer.Option(..., "--entries", help="Path to JSON file with TOC entries."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Generate a table of contents page and prepend it to the PDF.

    The entries JSON should be a list of objects with 'title' and 'page' keys.
    Example: [{"title": "Chapter 1", "page": 1}, {"title": "Chapter 2", "page": 5}]
    """
    import io
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas
    from makepdf.utils import ensure_pdf, output_path as _output_path, get_page_size

    try:
        src = ensure_pdf(str(input))
        out = _output_path(str(output), "toc.pdf")
        entries_data = _load_json(entries)
        if not isinstance(entries_data, list):
            typer.echo("Error: entries JSON must be a list of {title, page} objects.")
            raise typer.Exit(1)

        reader = PdfReader(str(src))

        # Determine page size from the first page of the source PDF
        first_page_box = reader.pages[0].mediabox
        page_w = float(first_page_box.width)
        page_h = float(first_page_box.height)

        # Create TOC page
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(page_w, page_h))
        c.setFont("Helvetica-Bold", 18)
        y = page_h - 72
        c.drawString(72, y, "Table of Contents")
        y -= 36

        c.setFont("Helvetica", 12)
        for entry in entries_data:
            title = entry.get("title", "")
            page_num = entry.get("page", "")
            line = f"{title} {'.' * 40} {page_num}"
            # Truncate if too long
            c.drawString(72, y, f"{title}")
            c.drawRightString(page_w - 72, y, str(page_num))
            # Draw dot leader
            dots_x_start = 72 + c.stringWidth(title, "Helvetica", 12) + 5
            dots_x_end = page_w - 72 - c.stringWidth(str(page_num), "Helvetica", 12) - 5
            if dots_x_start < dots_x_end:
                dots = "." * int((dots_x_end - dots_x_start) / c.stringWidth(".", "Helvetica", 12))
                c.drawString(dots_x_start, y, dots)
            y -= 20
            if y < 72:
                c.showPage()
                c.setFont("Helvetica", 12)
                y = page_h - 72

        c.save()
        buf.seek(0)

        toc_reader = PdfReader(buf)
        writer = PdfWriter()
        # Prepend TOC pages
        for page in toc_reader.pages:
            writer.add_page(page)
        # Append original pages
        for page in reader.pages:
            writer.add_page(page)

        with open(out, "wb") as f:
            writer.write(f)

        typer.echo(f"TOC generated. Saved: {out}")
    except MakePdfError as exc:
        _handle_error(exc)


@toc_app.command("extract")
def toc_extract_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF."),
) -> None:
    """Extract bookmarks/outlines from a PDF and print as JSON."""
    from pypdf import PdfReader
    from makepdf.utils import ensure_pdf

    try:
        src = ensure_pdf(str(input))
        reader = PdfReader(str(src))

        outlines = reader.outline
        if not outlines:
            typer.echo("No bookmarks/outlines found.")
            return

        def _flatten(items: list, depth: int = 0) -> list[dict]:
            result = []
            for item in items:
                if isinstance(item, list):
                    result.extend(_flatten(item, depth + 1))
                else:
                    title = item.title if hasattr(item, "title") else str(item.get("/Title", ""))
                    result.append({"title": title, "level": depth})
            return result

        flat = _flatten(outlines)
        typer.echo(json.dumps(flat, indent=2))
    except MakePdfError as exc:
        _handle_error(exc)


@toc_app.command("add-bookmarks")
def toc_add_bookmarks_cmd(
    input: Path = typer.Argument(..., help="Path to input PDF."),
    entries: str = typer.Option(..., "--entries", help="Path to JSON file with bookmark entries."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Add bookmarks/outlines to a PDF.

    The entries JSON should be a list of objects with 'title' and 'page' keys.
    Example: [{"title": "Chapter 1", "page": 1}, {"title": "Chapter 2", "page": 5}]
    """
    from pypdf import PdfReader, PdfWriter
    from makepdf.utils import ensure_pdf, output_path as _output_path

    try:
        src = ensure_pdf(str(input))
        out = _output_path(str(output), "bookmarked.pdf")
        entries_data = _load_json(entries)
        if not isinstance(entries_data, list):
            typer.echo("Error: entries JSON must be a list of {title, page} objects.")
            raise typer.Exit(1)

        reader = PdfReader(str(src))
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        # Copy metadata
        if reader.metadata:
            writer.add_metadata(reader.metadata)

        for entry in entries_data:
            title = entry.get("title", "Untitled")
            page_num = int(entry.get("page", 1)) - 1  # Convert to 0-based
            if 0 <= page_num < len(writer.pages):
                writer.add_outline_item(title, page_num)

        with open(out, "wb") as f:
            writer.write(f)

        typer.echo(f"Bookmarks added. Saved: {out}")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# REDACT commands
# ===================================================================


@redact_app.command("area")
def redact_area_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    page_num: int = typer.Argument(..., help="Page number (1-based)."),
    x: float = typer.Argument(..., help="X coordinate of area."),
    y: float = typer.Argument(..., help="Y coordinate of area."),
    width: float = typer.Argument(..., help="Width of area."),
    height: float = typer.Argument(..., help="Height of area."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Redact a rectangular area on a specific page."""
    from makepdf.core.redaction import redact_area

    try:
        result = redact_area(str(input_pdf), page_num, x, y, width, height, output=str(output))
        typer.echo(f"Redacted area on page {page_num}. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@redact_app.command("text")
def redact_text_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    search_term: str = typer.Argument(..., help="Text to search for and redact."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Find and redact all occurrences of a text string."""
    from makepdf.core.redaction import redact_text

    try:
        result = redact_text(str(input_pdf), search_term, output=str(output))
        typer.echo(f"Redacted text '{search_term}'. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@redact_app.command("patterns")
def redact_patterns_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    patterns: str = typer.Argument(..., help="Comma-separated list of regex patterns to redact."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Search and redact text matching regex patterns."""
    from makepdf.core.redaction import search_and_redact

    try:
        pattern_list = [p.strip() for p in patterns.split(",") if p.strip()]
        result = search_and_redact(str(input_pdf), pattern_list, output=str(output))
        typer.echo(f"Redacted {len(pattern_list)} pattern(s). Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# CROP commands
# ===================================================================


@crop_app.command("pages")
def crop_pages_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    left: float = typer.Argument(..., help="Left inset in points."),
    bottom: float = typer.Argument(..., help="Bottom inset in points."),
    right: float = typer.Argument(..., help="Right inset in points."),
    top: float = typer.Argument(..., help="Top inset in points."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    pages: Optional[str] = typer.Option(None, "--pages", help="Comma-separated page numbers."),
) -> None:
    """Crop pages by insetting each edge inward."""
    from makepdf.core.cropper import crop_pages

    try:
        page_list = _parse_pages(pages) if pages else None
        result = crop_pages(str(input_pdf), left, bottom, right, top, output=str(output), pages=page_list)
        typer.echo(f"Cropped pages. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@crop_app.command("resize")
def crop_resize_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    width: float = typer.Argument(..., help="Target width in points."),
    height: float = typer.Argument(..., help="Target height in points."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    pages: Optional[str] = typer.Option(None, "--pages", help="Comma-separated page numbers."),
) -> None:
    """Resize pages to the specified dimensions."""
    from makepdf.core.cropper import resize_pages

    try:
        page_list = _parse_pages(pages) if pages else None
        result = resize_pages(str(input_pdf), width, height, output=str(output), pages=page_list)
        typer.echo(f"Resized pages. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@crop_app.command("trim")
def crop_trim_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    margin: float = typer.Argument(..., help="Margin to trim from all sides in points."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Trim equal margins from all four sides of each page."""
    from makepdf.core.cropper import trim_margins

    try:
        result = trim_margins(str(input_pdf), margin, output=str(output))
        typer.echo(f"Trimmed margins. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# STAMP commands
# ===================================================================


@stamp_app.command("add")
def stamp_add_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    stamp_type: str = typer.Argument(..., help="Stamp type (e.g. APPROVED, DRAFT, CONFIDENTIAL)."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    position: str = typer.Option("center", "--position", help="Stamp position."),
    opacity: float = typer.Option(0.5, "--opacity", help="Stamp opacity (0-1)."),
) -> None:
    """Add a predefined stamp to PDF pages."""
    from makepdf.core.stamps import add_stamp

    try:
        result = add_stamp(str(input_pdf), stamp_type, output=str(output), position=position, opacity=opacity)
        typer.echo(f"Added '{stamp_type}' stamp. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@stamp_app.command("custom")
def stamp_custom_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    text: str = typer.Argument(..., help="Custom stamp text."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    font_size: float = typer.Option(36, "--font-size", help="Font size in points."),
    color_r: float = typer.Option(1, "--color-r", help="Red color component (0-1)."),
    color_g: float = typer.Option(0, "--color-g", help="Green color component (0-1)."),
    color_b: float = typer.Option(0, "--color-b", help="Blue color component (0-1)."),
) -> None:
    """Add a custom text stamp to PDF pages."""
    from makepdf.core.stamps import add_custom_stamp

    try:
        result = add_custom_stamp(str(input_pdf), text, output=str(output), font_size=font_size, color=(color_r, color_g, color_b))
        typer.echo(f"Added custom stamp '{text}'. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@stamp_app.command("image")
def stamp_image_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    image_path: Path = typer.Argument(..., help="Path to stamp image file."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    position: str = typer.Option("bottom-right", "--position", help="Stamp position."),
    scale: float = typer.Option(0.3, "--scale", help="Image scale factor."),
) -> None:
    """Add an image stamp to PDF pages."""
    from makepdf.core.stamps import add_image_stamp

    try:
        result = add_image_stamp(str(input_pdf), str(image_path), output=str(output), position=position, scale=scale)
        typer.echo(f"Added image stamp. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# BATES commands
# ===================================================================


@bates_app.command("add")
def bates_add_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    prefix: str = typer.Option("", "--prefix", help="Bates number prefix."),
    suffix: str = typer.Option("", "--suffix", help="Bates number suffix."),
    start: int = typer.Option(1, "--start", help="Starting number."),
    digits: int = typer.Option(6, "--digits", help="Number of digits."),
    position: str = typer.Option("bottom-center", "--position", help="Position on page."),
) -> None:
    """Add Bates numbers to a PDF."""
    from makepdf.core.bates import add_bates_numbers

    try:
        result = add_bates_numbers(str(input_pdf), output=str(output), prefix=prefix, suffix=suffix, start=start, digits=digits, position=position)
        typer.echo(f"Added Bates numbers. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@bates_app.command("batch")
def bates_batch_cmd(
    pdf_paths: str = typer.Argument(..., help="Comma-separated list of PDF file paths."),
    output_dir: Path = typer.Option(..., "-o", "--output-dir", help="Output directory."),
    prefix: str = typer.Option("", "--prefix", help="Bates number prefix."),
    start: int = typer.Option(1, "--start", help="Starting number."),
    digits: int = typer.Option(6, "--digits", help="Number of digits."),
) -> None:
    """Add Bates numbers to a batch of PDFs."""
    from makepdf.core.bates import add_bates_to_batch

    try:
        paths = [p.strip() for p in pdf_paths.split(",") if p.strip()]
        results = add_bates_to_batch(paths, output_dir=str(output_dir), prefix=prefix, start=start, digits=digits)
        for p in results:
            typer.echo(f"  {p}")
        typer.echo(f"Bates numbered {len(results)} file(s) in {output_dir}")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# COMPARE commands
# ===================================================================


@compare_app.command("text")
def compare_text_cmd(
    pdf_a: Path = typer.Argument(..., help="Path to first PDF."),
    pdf_b: Path = typer.Argument(..., help="Path to second PDF."),
) -> None:
    """Compare two PDFs by their extracted text content."""
    from makepdf.core.compare import compare_text

    try:
        result = compare_text(str(pdf_a), str(pdf_b))
        typer.echo(json.dumps(result, indent=2, default=str))
    except MakePdfError as exc:
        _handle_error(exc)


@compare_app.command("metadata")
def compare_metadata_cmd(
    pdf_a: Path = typer.Argument(..., help="Path to first PDF."),
    pdf_b: Path = typer.Argument(..., help="Path to second PDF."),
) -> None:
    """Compare the metadata of two PDF files."""
    from makepdf.core.compare import compare_metadata

    try:
        result = compare_metadata(str(pdf_a), str(pdf_b))
        typer.echo(json.dumps(result, indent=2, default=str))
    except MakePdfError as exc:
        _handle_error(exc)


@compare_app.command("structure")
def compare_structure_cmd(
    pdf_a: Path = typer.Argument(..., help="Path to first PDF."),
    pdf_b: Path = typer.Argument(..., help="Path to second PDF."),
) -> None:
    """Compare structural properties of two PDFs."""
    from makepdf.core.compare import compare_structure

    try:
        result = compare_structure(str(pdf_a), str(pdf_b))
        typer.echo(json.dumps(result, indent=2, default=str))
    except MakePdfError as exc:
        _handle_error(exc)


@compare_app.command("report")
def compare_report_cmd(
    pdf_a: Path = typer.Argument(..., help="Path to first PDF."),
    pdf_b: Path = typer.Argument(..., help="Path to second PDF."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF report path."),
) -> None:
    """Generate a PDF diff report comparing two documents."""
    from makepdf.core.compare import generate_diff_report

    try:
        result = generate_diff_report(str(pdf_a), str(pdf_b), output=str(output))
        typer.echo(f"Diff report generated. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# FLATTEN commands
# ===================================================================


@flatten_app.command("forms")
def flatten_forms_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Flatten all form fields, making them non-editable."""
    from makepdf.core.flatten import flatten_forms

    try:
        result = flatten_forms(str(input_pdf), output=str(output))
        typer.echo(f"Flattened forms. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@flatten_app.command("annotations")
def flatten_annotations_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Flatten all annotations into static page content."""
    from makepdf.core.flatten import flatten_annotations

    try:
        result = flatten_annotations(str(input_pdf), output=str(output))
        typer.echo(f"Flattened annotations. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@flatten_app.command("all")
def flatten_all_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Flatten both form fields and annotations."""
    from makepdf.core.flatten import flatten_all

    try:
        result = flatten_all(str(input_pdf), output=str(output))
        typer.echo(f"Flattened all. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# METADATA commands
# ===================================================================


@meta_app.command("get")
def metadata_get_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
) -> None:
    """Extract and display all metadata from a PDF."""
    from makepdf.core.metadata import get_metadata

    try:
        result = get_metadata(str(input_pdf))
        typer.echo(json.dumps(result, indent=2, default=str))
    except MakePdfError as exc:
        _handle_error(exc)


@meta_app.command("set")
def metadata_set_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    title: Optional[str] = typer.Option(None, "--title", help="Document title."),
    author: Optional[str] = typer.Option(None, "--author", help="Document author."),
    subject: Optional[str] = typer.Option(None, "--subject", help="Document subject."),
    keywords: Optional[str] = typer.Option(None, "--keywords", help="Comma-separated keywords."),
) -> None:
    """Set metadata fields on a PDF."""
    from makepdf.core.metadata import set_metadata

    try:
        result = set_metadata(str(input_pdf), output=str(output), title=title, author=author, subject=subject, keywords=keywords)
        typer.echo(f"Metadata updated. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@meta_app.command("remove")
def metadata_remove_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Strip all metadata from a PDF."""
    from makepdf.core.metadata import remove_metadata

    try:
        result = remove_metadata(str(input_pdf), output=str(output))
        typer.echo(f"Metadata removed. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# ATTACH commands
# ===================================================================


@attach_app.command("add")
def attach_add_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    file_path: Path = typer.Argument(..., help="Path to file to attach."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    description: str = typer.Option("", "--description", help="Attachment description."),
) -> None:
    """Embed a file attachment into a PDF."""
    from makepdf.core.attachments import add_attachment

    try:
        result = add_attachment(str(input_pdf), str(file_path), output=str(output), description=description)
        typer.echo(f"Attachment added. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@attach_app.command("extract")
def attach_extract_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    output_dir: Path = typer.Option(..., "-o", "--output-dir", help="Output directory for attachments."),
) -> None:
    """Extract all embedded file attachments from a PDF."""
    from makepdf.core.attachments import extract_attachments

    try:
        results = extract_attachments(str(input_pdf), str(output_dir))
        for p in results:
            typer.echo(f"  {p}")
        typer.echo(f"Extracted {len(results)} attachment(s) to {output_dir}")
    except MakePdfError as exc:
        _handle_error(exc)


@attach_app.command("list")
def attach_list_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
) -> None:
    """List all embedded file attachments in a PDF."""
    from makepdf.core.attachments import list_attachments

    try:
        result = list_attachments(str(input_pdf))
        typer.echo(json.dumps(result, indent=2, default=str))
    except MakePdfError as exc:
        _handle_error(exc)


@attach_app.command("remove")
def attach_remove_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Remove all embedded file attachments from a PDF."""
    from makepdf.core.attachments import remove_attachments

    try:
        result = remove_attachments(str(input_pdf), output=str(output))
        typer.echo(f"Attachments removed. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# LINK commands
# ===================================================================


@link_app.command("add")
def link_add_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    page_num: int = typer.Argument(..., help="Page number (1-based)."),
    x: float = typer.Argument(..., help="X coordinate."),
    y: float = typer.Argument(..., help="Y coordinate."),
    width: float = typer.Argument(..., help="Link area width."),
    height: float = typer.Argument(..., help="Link area height."),
    url: str = typer.Argument(..., help="Target URL."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Add a hyperlink to a PDF page."""
    from makepdf.core.links import add_link

    try:
        result = add_link(str(input_pdf), page_num, x, y, width, height, url, output=str(output))
        typer.echo(f"Link added on page {page_num}. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@link_app.command("internal")
def link_internal_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    from_page: int = typer.Argument(..., help="Source page number (1-based)."),
    x: float = typer.Argument(..., help="X coordinate."),
    y: float = typer.Argument(..., help="Y coordinate."),
    width: float = typer.Argument(..., help="Link area width."),
    height: float = typer.Argument(..., help="Link area height."),
    to_page: int = typer.Argument(..., help="Destination page number (1-based)."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Add an internal page-navigation link."""
    from makepdf.core.links import add_internal_link

    try:
        result = add_internal_link(str(input_pdf), from_page, x, y, width, height, to_page, output=str(output))
        typer.echo(f"Internal link added (page {from_page} -> {to_page}). Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@link_app.command("extract")
def link_extract_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
) -> None:
    """Extract all links from a PDF."""
    from makepdf.core.links import extract_links

    try:
        result = extract_links(str(input_pdf))
        typer.echo(json.dumps(result, indent=2, default=str))
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# LABEL commands
# ===================================================================


@label_app.command("set")
def label_set_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    labels_json: str = typer.Argument(..., help="Path to JSON file with label definitions."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Set page labels (numbering schemes) on a PDF."""
    from makepdf.core.page_labels import set_page_labels

    try:
        labels = _load_json(labels_json)
        if not isinstance(labels, list):
            typer.echo("Error: labels JSON must be a list of label-range objects.")
            raise typer.Exit(1)
        result = set_page_labels(str(input_pdf), labels, output=str(output))
        typer.echo(f"Page labels set. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@label_app.command("get")
def label_get_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
) -> None:
    """Extract the current page label configuration from a PDF."""
    from makepdf.core.page_labels import get_page_labels

    try:
        result = get_page_labels(str(input_pdf))
        typer.echo(json.dumps(result, indent=2, default=str))
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# OPTIMIZE commands
# ===================================================================


@opt_app.command("run")
def optimize_run_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    remove_duplication: bool = typer.Option(True, "--remove-duplication/--no-remove-duplication", help="Remove duplicate objects."),
    remove_metadata: bool = typer.Option(False, "--remove-metadata/--no-remove-metadata", help="Remove metadata."),
    compress_streams: bool = typer.Option(True, "--compress-streams/--no-compress-streams", help="Compress streams."),
) -> None:
    """Optimize a PDF for reduced file size."""
    from makepdf.core.optimizer import optimize

    try:
        result = optimize(str(input_pdf), output=str(output), remove_duplication=remove_duplication, remove_metadata=remove_metadata, compress_streams=compress_streams)
        typer.echo(f"Optimized PDF. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@opt_app.command("cleanup")
def optimize_cleanup_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Remove unused objects from a PDF."""
    from makepdf.core.optimizer import remove_unused_objects

    try:
        result = remove_unused_objects(str(input_pdf), output=str(output))
        typer.echo(f"Cleaned up unused objects. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@opt_app.command("linearize")
def optimize_linearize_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Optimize a PDF for fast web viewing."""
    from makepdf.core.optimizer import linearize

    try:
        result = linearize(str(input_pdf), output=str(output))
        typer.echo(f"Linearized PDF. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@opt_app.command("report")
def optimize_report_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
) -> None:
    """Analyze a PDF and show optimization suggestions."""
    from makepdf.core.optimizer import get_optimization_report

    try:
        result = get_optimization_report(str(input_pdf))
        typer.echo(json.dumps(result, indent=2, default=str))
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# A11Y (accessibility) commands
# ===================================================================


@a11y_app.command("set-language")
def a11y_set_language_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    language: str = typer.Argument(..., help="Language tag (e.g. en-US, de-DE)."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Set the document language in the PDF catalog."""
    from makepdf.core.accessibility import set_language

    try:
        result = set_language(str(input_pdf), language, output=str(output))
        typer.echo(f"Language set to '{language}'. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@a11y_app.command("get-language")
def a11y_get_language_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
) -> None:
    """Get the document language from the PDF catalog."""
    from makepdf.core.accessibility import get_language

    try:
        result = get_language(str(input_pdf))
        if result:
            typer.echo(f"Document language: {result}")
        else:
            typer.echo("No document language set.")
    except MakePdfError as exc:
        _handle_error(exc)


@a11y_app.command("title-display")
def a11y_title_display_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    display_title: bool = typer.Option(True, "--display-title/--no-display-title", help="Show title in title bar."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Set whether the title bar shows the document title or filename."""
    from makepdf.core.accessibility import set_title_display

    try:
        result = set_title_display(str(input_pdf), display_title=display_title, output=str(output))
        typer.echo(f"Title display set to {display_title}. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@a11y_app.command("check")
def a11y_check_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
) -> None:
    """Check a PDF for basic accessibility issues."""
    from makepdf.core.accessibility import check_accessibility

    try:
        result = check_accessibility(str(input_pdf))
        typer.echo(json.dumps(result, indent=2, default=str))
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# MARKUP commands
# ===================================================================


@markup_app.command("highlight")
def markup_highlight_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    page_num: int = typer.Argument(..., help="Page number (1-based)."),
    x: float = typer.Argument(..., help="X coordinate."),
    y: float = typer.Argument(..., help="Y coordinate."),
    width: float = typer.Argument(..., help="Area width."),
    height: float = typer.Argument(..., help="Area height."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
    color_r: float = typer.Option(1, "--color-r", help="Red color component (0-1)."),
    color_g: float = typer.Option(1, "--color-g", help="Green color component (0-1)."),
    color_b: float = typer.Option(0, "--color-b", help="Blue color component (0-1)."),
) -> None:
    """Add a highlight annotation over a rectangular area."""
    from makepdf.core.markup import highlight_area

    try:
        result = highlight_area(str(input_pdf), page_num, x, y, width, height, output=str(output), color=(color_r, color_g, color_b))
        typer.echo(f"Highlight added on page {page_num}. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@markup_app.command("underline")
def markup_underline_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    page_num: int = typer.Argument(..., help="Page number (1-based)."),
    x: float = typer.Argument(..., help="X coordinate."),
    y: float = typer.Argument(..., help="Y coordinate."),
    width: float = typer.Argument(..., help="Area width."),
    height: float = typer.Argument(..., help="Area height."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Add an underline annotation over a rectangular area."""
    from makepdf.core.markup import underline_area

    try:
        result = underline_area(str(input_pdf), page_num, x, y, width, height, output=str(output))
        typer.echo(f"Underline added on page {page_num}. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@markup_app.command("strikethrough")
def markup_strikethrough_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    page_num: int = typer.Argument(..., help="Page number (1-based)."),
    x: float = typer.Argument(..., help="X coordinate."),
    y: float = typer.Argument(..., help="Y coordinate."),
    width: float = typer.Argument(..., help="Area width."),
    height: float = typer.Argument(..., help="Area height."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Add a strikethrough annotation over a rectangular area."""
    from makepdf.core.markup import strikethrough_area

    try:
        result = strikethrough_area(str(input_pdf), page_num, x, y, width, height, output=str(output))
        typer.echo(f"Strikethrough added on page {page_num}. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@markup_app.command("note")
def markup_note_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    page_num: int = typer.Argument(..., help="Page number (1-based)."),
    x: float = typer.Argument(..., help="X coordinate."),
    y: float = typer.Argument(..., help="Y coordinate."),
    text: str = typer.Argument(..., help="Sticky note text."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Add a sticky note annotation at a point on a page."""
    from makepdf.core.markup import add_sticky_note

    try:
        result = add_sticky_note(str(input_pdf), page_num, x, y, text, output=str(output))
        typer.echo(f"Sticky note added on page {page_num}. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


@markup_app.command("comment")
def markup_comment_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    page_num: int = typer.Argument(..., help="Page number (1-based)."),
    x: float = typer.Argument(..., help="X coordinate."),
    y: float = typer.Argument(..., help="Y coordinate."),
    width: float = typer.Argument(..., help="Comment area width."),
    height: float = typer.Argument(..., help="Comment area height."),
    text: str = typer.Argument(..., help="Comment text."),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Add a text comment annotation to a rectangular area."""
    from makepdf.core.markup import add_text_comment

    try:
        result = add_text_comment(str(input_pdf), page_num, x, y, width, height, text, output=str(output))
        typer.echo(f"Comment added on page {page_num}. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# REORDER command (top-level)
# ===================================================================


@app.command("reorder")
def reorder_cmd(
    input_pdf: Path = typer.Argument(..., help="Path to input PDF."),
    order: str = typer.Option(..., "--order", help='Comma-separated page order, e.g. "3,1,2".'),
    output: Path = typer.Option(..., "-o", "--output", help="Output PDF path."),
) -> None:
    """Reorder pages in a PDF according to a custom sequence."""
    from makepdf.core.merger import reorder_pages

    try:
        page_order = _parse_pages(order)
        result = reorder_pages(str(input_pdf), page_order, output=str(output))
        typer.echo(f"Pages reordered. Saved: {result}")
    except MakePdfError as exc:
        _handle_error(exc)


# ===================================================================
# WEB command
# ===================================================================


@app.command("web")
def web_cmd(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to."),
    port: int = typer.Option(8000, "--port", help="Port to listen on."),
) -> None:
    """Start the MakePDF web server."""
    try:
        import uvicorn
    except ImportError:
        typer.echo("Error: uvicorn is required for the web server. Install with: pip install uvicorn")
        raise typer.Exit(1)

    try:
        from makepdf.web.app import app as web_app  # type: ignore[import-not-found]
    except ImportError:
        typer.echo("Error: web module not found. Ensure makepdf.web is installed.")
        raise typer.Exit(1)

    typer.echo(f"Starting MakePDF web server on {host}:{port}")
    uvicorn.run(web_app, host=host, port=port)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
