"""Text markup and annotation features using pypdf.

Provides tools for adding highlight, underline, and strikethrough markup
annotations as well as sticky notes and free-text comments — similar to
Adobe Acrobat's commenting and markup tools.
"""

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf, output_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_VALID_STICKY_ICONS = frozenset({
    "Comment", "Key", "Note", "Help",
    "NewParagraph", "Paragraph", "Insert",
})


def _validate_page(reader: PdfReader, page_num: int) -> None:
    """Raise ``InputError`` if *page_num* is out of range (0-indexed)."""
    if page_num < 0 or page_num >= len(reader.pages):
        raise InputError(
            f"Page number {page_num} is out of range. "
            f"Document has {len(reader.pages)} page(s) (0-indexed)."
        )


def _color_array(color: tuple[float, float, float]) -> ArrayObject:
    """Convert an ``(r, g, b)`` tuple to a PDF ``ArrayObject``."""
    return ArrayObject([FloatObject(c) for c in color])


def _quad_points(
    x: float, y: float, width: float, height: float,
) -> ArrayObject:
    """Build ``/QuadPoints`` for a rectangle.

    QuadPoints defines the quadrilateral in the order:
    ``[x1 y1 x2 y2 x3 y3 x4 y4]`` where the points go
    bottom-left, bottom-right, top-right, top-left  (per the PDF spec the
    order is actually: upper-left, upper-right, lower-left, lower-right).
    """
    x1, y1 = x, y + height          # upper-left
    x2, y2 = x + width, y + height  # upper-right
    x3, y3 = x, y                   # lower-left
    x4, y4 = x + width, y           # lower-right
    return ArrayObject([
        FloatObject(x1), FloatObject(y1),
        FloatObject(x2), FloatObject(y2),
        FloatObject(x3), FloatObject(y3),
        FloatObject(x4), FloatObject(y4),
    ])


def _rect_array(
    x: float, y: float, width: float, height: float,
) -> ArrayObject:
    """Build a ``/Rect`` array ``[x, y, x+width, y+height]``."""
    return ArrayObject([
        FloatObject(x),
        FloatObject(y),
        FloatObject(x + width),
        FloatObject(y + height),
    ])


def _add_annotation_to_page(writer: PdfWriter, page_num: int, annot: DictionaryObject) -> None:
    """Append an annotation dictionary to a page's ``/Annots`` array."""
    page = writer.pages[page_num]

    if "/Annots" not in page:
        page[NameObject("/Annots")] = ArrayObject()

    annots = page["/Annots"]
    if not isinstance(annots, ArrayObject):
        annots = ArrayObject(annots)
        page[NameObject("/Annots")] = annots

    annots.append(annot)


def _build_writer(input_pdf: str | Path) -> tuple[Path, PdfReader, PdfWriter]:
    """Read a PDF and prepare a writer with all pages and metadata copied."""
    pdf_path = ensure_pdf(input_pdf)
    reader = PdfReader(pdf_path)
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    if reader.metadata:
        writer.add_metadata(reader.metadata)

    return pdf_path, reader, writer


def _write_output(writer: PdfWriter, out: Path) -> Path:
    """Write the ``PdfWriter`` to *out* and return the path."""
    with open(out, "wb") as f:
        writer.write(f)
    return out


# ---------------------------------------------------------------------------
# Markup annotations
# ---------------------------------------------------------------------------

def _add_markup_annotation(
    input_pdf: str | Path,
    page_num: int,
    x: float,
    y: float,
    width: float,
    height: float,
    subtype: str,
    output: str | Path | None,
    color: tuple[float, float, float],
    default_suffix: str,
) -> Path:
    """Shared implementation for highlight, underline, and strikethrough."""
    pdf_path, reader, writer = _build_writer(input_pdf)
    _validate_page(reader, page_num)

    out = output_path(output, pdf_path.stem + default_suffix)

    annot = DictionaryObject()
    annot[NameObject("/Type")] = NameObject("/Annot")
    annot[NameObject("/Subtype")] = NameObject(subtype)
    annot[NameObject("/Rect")] = _rect_array(x, y, width, height)
    annot[NameObject("/QuadPoints")] = _quad_points(x, y, width, height)
    annot[NameObject("/C")] = _color_array(color)
    annot[NameObject("/CA")] = FloatObject(1.0)
    annot[NameObject("/T")] = TextStringObject("MakePDF")
    annot[NameObject("/Contents")] = TextStringObject("")
    annot[NameObject("/F")] = NumberObject(4)  # Print flag

    _add_annotation_to_page(writer, page_num, annot)

    return _write_output(writer, out)


def highlight_area(
    input_pdf: str | Path,
    page_num: int,
    x: float,
    y: float,
    width: float,
    height: float,
    output: str | Path | None = None,
    color: tuple[float, float, float] = (1, 1, 0),
) -> Path:
    """Add a highlight annotation over a rectangular area on a page.

    Creates a ``/Highlight`` markup annotation that visually highlights
    the specified region, similar to using a highlighter pen.

    Args:
        input_pdf: Path to the source PDF file.
        page_num: Zero-indexed page number to annotate.
        x: Left edge of the highlight rectangle (in PDF points).
        y: Bottom edge of the highlight rectangle (in PDF points).
        width: Width of the highlight area (in PDF points).
        height: Height of the highlight area (in PDF points).
        output: Path for the output PDF.  If ``None``, a default name
            derived from the input is used.
        color: RGB color tuple with components in the ``[0, 1]`` range.
            Defaults to yellow ``(1, 1, 0)``.

    Returns:
        Path to the written PDF.

    Raises:
        InputError: If the input file is invalid or *page_num* is out of
            range.
    """
    return _add_markup_annotation(
        input_pdf, page_num, x, y, width, height,
        subtype="/Highlight",
        output=output,
        color=color,
        default_suffix="_highlighted.pdf",
    )


def underline_area(
    input_pdf: str | Path,
    page_num: int,
    x: float,
    y: float,
    width: float,
    height: float,
    output: str | Path | None = None,
    color: tuple[float, float, float] = (0, 0, 1),
) -> Path:
    """Add an underline annotation over a rectangular area on a page.

    Creates an ``/Underline`` markup annotation that draws a line
    beneath the specified region.

    Args:
        input_pdf: Path to the source PDF file.
        page_num: Zero-indexed page number to annotate.
        x: Left edge of the underline rectangle (in PDF points).
        y: Bottom edge of the underline rectangle (in PDF points).
        width: Width of the underline area (in PDF points).
        height: Height of the underline area (in PDF points).
        output: Path for the output PDF.  If ``None``, a default name
            derived from the input is used.
        color: RGB color tuple with components in the ``[0, 1]`` range.
            Defaults to blue ``(0, 0, 1)``.

    Returns:
        Path to the written PDF.

    Raises:
        InputError: If the input file is invalid or *page_num* is out of
            range.
    """
    return _add_markup_annotation(
        input_pdf, page_num, x, y, width, height,
        subtype="/Underline",
        output=output,
        color=color,
        default_suffix="_underlined.pdf",
    )


def strikethrough_area(
    input_pdf: str | Path,
    page_num: int,
    x: float,
    y: float,
    width: float,
    height: float,
    output: str | Path | None = None,
    color: tuple[float, float, float] = (1, 0, 0),
) -> Path:
    """Add a strikethrough annotation over a rectangular area on a page.

    Creates a ``/StrikeOut`` markup annotation that draws a line through
    the middle of the specified region.

    Args:
        input_pdf: Path to the source PDF file.
        page_num: Zero-indexed page number to annotate.
        x: Left edge of the strikethrough rectangle (in PDF points).
        y: Bottom edge of the strikethrough rectangle (in PDF points).
        width: Width of the strikethrough area (in PDF points).
        height: Height of the strikethrough area (in PDF points).
        output: Path for the output PDF.  If ``None``, a default name
            derived from the input is used.
        color: RGB color tuple with components in the ``[0, 1]`` range.
            Defaults to red ``(1, 0, 0)``.

    Returns:
        Path to the written PDF.

    Raises:
        InputError: If the input file is invalid or *page_num* is out of
            range.
    """
    return _add_markup_annotation(
        input_pdf, page_num, x, y, width, height,
        subtype="/StrikeOut",
        output=output,
        color=color,
        default_suffix="_strikethrough.pdf",
    )


# ---------------------------------------------------------------------------
# Sticky note
# ---------------------------------------------------------------------------

def add_sticky_note(
    input_pdf: str | Path,
    page_num: int,
    x: float,
    y: float,
    text: str,
    output: str | Path | None = None,
    color: tuple[float, float, float] = (1, 1, 0),
    icon: str = "Comment",
) -> Path:
    """Add a sticky note (pop-up comment) annotation at a point on a page.

    Creates a ``/Text`` annotation — the familiar sticky-note icon that
    opens a pop-up when clicked.

    Args:
        input_pdf: Path to the source PDF file.
        page_num: Zero-indexed page number to annotate.
        x: Horizontal position of the note icon (in PDF points).
        y: Vertical position of the note icon (in PDF points).
        text: The note content displayed in the pop-up.
        output: Path for the output PDF.  If ``None``, a default name
            derived from the input is used.
        color: RGB color tuple with components in the ``[0, 1]`` range.
            Defaults to yellow ``(1, 1, 0)``.
        icon: Name of the icon to display.  One of ``"Comment"``,
            ``"Key"``, ``"Note"``, ``"Help"``, ``"NewParagraph"``,
            ``"Paragraph"``, or ``"Insert"``.  Defaults to ``"Comment"``.

    Returns:
        Path to the written PDF.

    Raises:
        InputError: If the input file is invalid or *page_num* is out of
            range.
        ValueError: If *icon* is not a recognised icon name.
    """
    if icon not in _VALID_STICKY_ICONS:
        raise ValueError(
            f"Invalid icon '{icon}'. Choose from: {sorted(_VALID_STICKY_ICONS)}"
        )

    pdf_path, reader, writer = _build_writer(input_pdf)
    _validate_page(reader, page_num)

    out = output_path(output, pdf_path.stem + "_noted.pdf")

    # Sticky notes use a small fixed rectangle around the icon position.
    icon_size = 24
    annot = DictionaryObject()
    annot[NameObject("/Type")] = NameObject("/Annot")
    annot[NameObject("/Subtype")] = NameObject("/Text")
    annot[NameObject("/Rect")] = ArrayObject([
        FloatObject(x),
        FloatObject(y),
        FloatObject(x + icon_size),
        FloatObject(y + icon_size),
    ])
    annot[NameObject("/Contents")] = TextStringObject(text)
    annot[NameObject("/C")] = _color_array(color)
    annot[NameObject("/CA")] = FloatObject(1.0)
    annot[NameObject("/T")] = TextStringObject("MakePDF")
    annot[NameObject("/Name")] = NameObject(f"/{icon}")
    annot[NameObject("/F")] = NumberObject(4)  # Print flag
    annot[NameObject("/Open")] = NameObject("/false")

    _add_annotation_to_page(writer, page_num, annot)

    return _write_output(writer, out)


# ---------------------------------------------------------------------------
# Free text annotation (text box / comment)
# ---------------------------------------------------------------------------

def add_text_comment(
    input_pdf: str | Path,
    page_num: int,
    x: float,
    y: float,
    width: float,
    height: float,
    text: str,
    output: str | Path | None = None,
    color: tuple[float, float, float] = (1, 1, 0),
    font_size: int | float = 10,
) -> Path:
    """Add a free-text annotation (text box) on a page.

    Creates a ``/FreeText`` annotation that renders text directly on the
    page surface within the specified rectangle, without requiring the
    user to click an icon.

    Args:
        input_pdf: Path to the source PDF file.
        page_num: Zero-indexed page number to annotate.
        x: Left edge of the text box (in PDF points).
        y: Bottom edge of the text box (in PDF points).
        width: Width of the text box (in PDF points).
        height: Height of the text box (in PDF points).
        text: The text to display in the annotation.
        output: Path for the output PDF.  If ``None``, a default name
            derived from the input is used.
        color: RGB background color tuple with components in the
            ``[0, 1]`` range.  Defaults to yellow ``(1, 1, 0)``.
        font_size: Font size in points.  Defaults to ``10``.

    Returns:
        Path to the written PDF.

    Raises:
        InputError: If the input file is invalid or *page_num* is out of
            range.
    """
    pdf_path, reader, writer = _build_writer(input_pdf)
    _validate_page(reader, page_num)

    out = output_path(output, pdf_path.stem + "_commented.pdf")

    da_string = f"/Helv {font_size} Tf 0 0 0 rg"  # black text, Helvetica

    annot = DictionaryObject()
    annot[NameObject("/Type")] = NameObject("/Annot")
    annot[NameObject("/Subtype")] = NameObject("/FreeText")
    annot[NameObject("/Rect")] = _rect_array(x, y, width, height)
    annot[NameObject("/Contents")] = TextStringObject(text)
    annot[NameObject("/C")] = _color_array(color)
    annot[NameObject("/CA")] = FloatObject(1.0)
    annot[NameObject("/T")] = TextStringObject("MakePDF")
    annot[NameObject("/DA")] = TextStringObject(da_string)
    annot[NameObject("/F")] = NumberObject(4)  # Print flag
    annot[NameObject("/Q")] = NumberObject(0)  # Left-aligned

    _add_annotation_to_page(writer, page_num, annot)

    return _write_output(writer, out)
