"""PDF creation from various source formats."""

from pathlib import Path

from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader

from makepdf.exceptions import InputError, DependencyError
from makepdf.utils import output_path, get_page_size
from makepdf.config import DEFAULT_FONT, DEFAULT_FONT_SIZE


def from_text(
    text: str,
    output: str | Path,
    font: str = "Helvetica",
    font_size: int = 12,
    page_size: str = "A4",
) -> Path:
    """Create a PDF from plain text.

    Uses reportlab Paragraph and SimpleDocTemplate to handle automatic
    line wrapping and page breaks.
    """
    if not text:
        raise InputError("Text content must not be empty")

    out = output_path(output, "output.pdf")
    rl_page_size = get_page_size(page_size)

    doc = SimpleDocTemplate(
        str(out),
        pagesize=rl_page_size,
        leftMargin=72,
        rightMargin=72,
        topMargin=72,
        bottomMargin=72,
    )

    style = ParagraphStyle(
        "CustomBody",
        parent=getSampleStyleSheet()["Normal"],
        fontName=font,
        fontSize=font_size,
        leading=font_size * 1.2,
        spaceAfter=font_size * 0.5,
    )

    story = []
    # Split on newlines so each line becomes its own paragraph, preserving
    # the original line structure while still allowing word-wrap within lines.
    for line in text.split("\n"):
        if line.strip() == "":
            story.append(Spacer(1, font_size * 0.8))
        else:
            # Escape XML-special characters so reportlab doesn't choke
            safe = (
                line.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            story.append(Paragraph(safe, style))

    doc.build(story)
    return out


def from_html(
    html_content: str,
    output: str | Path,
    page_size: str = "A4",
) -> Path:
    """Create a PDF from an HTML string.

    Requires WeasyPrint to be installed.
    """
    if not html_content:
        raise InputError("HTML content must not be empty")

    try:
        from weasyprint import HTML
    except ImportError:
        raise DependencyError(
            "WeasyPrint is required for HTML-to-PDF conversion. "
            "Install it with: pip install weasyprint"
        )

    out = output_path(output, "output.pdf")

    # Map page size names to CSS dimensions
    css_sizes = {
        "A3": "297mm 420mm",
        "A4": "210mm 297mm",
        "A5": "148mm 210mm",
        "LETTER": "8.5in 11in",
        "LEGAL": "8.5in 14in",
    }
    size_name = page_size.upper()
    css_dim = css_sizes.get(size_name)
    if css_dim is None:
        raise InputError(
            f"Unknown page size: {page_size}. "
            f"Options: {list(css_sizes.keys())}"
        )

    # Inject a @page rule to control page size
    page_css = f"@page {{ size: {css_dim}; margin: 1in; }}"
    styled_html = f"<style>{page_css}</style>{html_content}"

    HTML(string=styled_html).write_pdf(str(out))
    return out


def from_markdown(
    md_content: str,
    output: str | Path,
    page_size: str = "A4",
) -> Path:
    """Create a PDF from a Markdown string.

    Converts Markdown to HTML using the ``markdown`` library, then
    delegates to :func:`from_html`.
    """
    if not md_content:
        raise InputError("Markdown content must not be empty")

    try:
        import markdown
    except ImportError:
        raise DependencyError(
            "The 'markdown' library is required for Markdown-to-PDF conversion. "
            "Install it with: pip install markdown"
        )

    html = markdown.markdown(
        md_content,
        extensions=["tables", "fenced_code", "codehilite", "toc"],
    )

    # Wrap in a minimal HTML document with sensible default styling
    full_html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<style>"
        "body { font-family: Helvetica, Arial, sans-serif; font-size: 12pt; "
        "line-height: 1.4; color: #222; }"
        "pre, code { background: #f4f4f4; padding: 2px 6px; font-size: 10pt; }"
        "pre { padding: 12px; }"
        "table { border-collapse: collapse; width: 100%; }"
        "th, td { border: 1px solid #ccc; padding: 6px 10px; text-align: left; }"
        "th { background: #eee; }"
        "</style></head><body>"
        f"{html}"
        "</body></html>"
    )

    return from_html(full_html, output, page_size=page_size)


def from_images(
    image_paths: list[str | Path],
    output: str | Path,
    page_size: str = "A4",
) -> Path:
    """Create a PDF with one image per page.

    Each image is scaled to fit within the page margins while preserving
    its aspect ratio.
    """
    if not image_paths:
        raise InputError("At least one image path is required")

    out = output_path(output, "output.pdf")
    rl_page_size = get_page_size(page_size)
    page_w, page_h = rl_page_size

    margin = 72  # 1 inch
    avail_w = page_w - 2 * margin
    avail_h = page_h - 2 * margin

    c = Canvas(str(out), pagesize=rl_page_size)

    for idx, img_path in enumerate(image_paths):
        path = Path(img_path)
        if not path.exists():
            raise InputError(f"Image file not found: {path}")

        img = ImageReader(str(path))
        img_w, img_h = img.getSize()

        # Scale to fit the available area while keeping aspect ratio
        scale = min(avail_w / img_w, avail_h / img_h, 1.0)
        draw_w = img_w * scale
        draw_h = img_h * scale

        # Center the image on the page
        x = margin + (avail_w - draw_w) / 2
        y = margin + (avail_h - draw_h) / 2

        c.drawImage(
            img,
            x,
            y,
            width=draw_w,
            height=draw_h,
            preserveAspectRatio=True,
            anchor="c",
        )

        # Start a new page for every image except the last
        if idx < len(image_paths) - 1:
            c.showPage()

    c.save()
    return out


def from_template(
    template: dict,
    data: dict,
    output: str | Path,
) -> Path:
    """Create a PDF from a template definition and data dictionary.

    The *template* must contain a ``"pages"`` key whose value is a list of
    page definitions.  Each page is a dict with an ``"elements"`` list and
    an optional ``"page_size"`` (defaults to ``"A4"``).

    Each element dict must include:
        ``"type"``  -- one of ``"text"``, ``"image"``, ``"rect"``, ``"line"``
        ``"x"``, ``"y"`` -- position in points (origin = bottom-left)

    **Type-specific properties:**

    text
        ``"content"`` (str, may contain ``{key}`` placeholders resolved
        against *data*), ``"font"`` (default Helvetica),
        ``"font_size"`` (default 12), ``"color"`` (hex string, default
        ``"#000000"``).

    image
        ``"path"`` (str), ``"width"`` and ``"height"`` (both in points).

    rect
        ``"width"``, ``"height"``, optional ``"fill"`` (hex color),
        optional ``"stroke"`` (hex color), optional ``"stroke_width"``
        (default 1).

    line
        ``"x2"``, ``"y2"`` (end point), optional ``"stroke"`` (hex),
        optional ``"stroke_width"`` (default 1).
    """
    if not isinstance(template, dict) or "pages" not in template:
        raise InputError("Template must be a dict with a 'pages' key")

    pages = template["pages"]
    if not pages:
        raise InputError("Template must contain at least one page")

    out = output_path(output, "output.pdf")

    # Use the first page's size as the initial canvas size
    first_size = get_page_size(pages[0].get("page_size", "A4"))
    c = Canvas(str(out), pagesize=first_size)

    for page_idx, page_def in enumerate(pages):
        pg_size = get_page_size(page_def.get("page_size", "A4"))
        c.setPageSize(pg_size)

        elements = page_def.get("elements", [])
        for elem in elements:
            etype = elem.get("type")
            x = elem.get("x", 0)
            y = elem.get("y", 0)

            if etype == "text":
                _draw_text(c, elem, x, y, data)
            elif etype == "image":
                _draw_image(c, elem, x, y)
            elif etype == "rect":
                _draw_rect(c, elem, x, y)
            elif etype == "line":
                _draw_line(c, elem, x, y)
            else:
                raise InputError(
                    f"Unknown element type '{etype}' on page {page_idx + 1}"
                )

        if page_idx < len(pages) - 1:
            c.showPage()

    c.save()
    return out


# ---------------------------------------------------------------------------
# Private helpers for from_template
# ---------------------------------------------------------------------------

def _hex_to_color(hex_str: str):
    """Convert a hex colour string like ``'#ff8800'`` to an RGB tuple (0-1)."""
    hex_str = hex_str.lstrip("#")
    if len(hex_str) != 6:
        raise InputError(f"Invalid hex color: #{hex_str}")
    r = int(hex_str[0:2], 16) / 255.0
    g = int(hex_str[2:4], 16) / 255.0
    b = int(hex_str[4:6], 16) / 255.0
    return (r, g, b)


def _draw_text(c: Canvas, elem: dict, x: float, y: float, data: dict):
    content = elem.get("content", "")
    # Resolve placeholders from data
    try:
        content = content.format(**data)
    except KeyError:
        pass  # leave unresolved placeholders as-is

    font = elem.get("font", DEFAULT_FONT)
    font_size = elem.get("font_size", DEFAULT_FONT_SIZE)
    color = elem.get("color", "#000000")

    c.saveState()
    c.setFont(font, font_size)
    c.setFillColorRGB(*_hex_to_color(color))
    c.drawString(x, y, content)
    c.restoreState()


def _draw_image(c: Canvas, elem: dict, x: float, y: float):
    path = elem.get("path")
    if not path:
        raise InputError("Image element requires a 'path' property")
    p = Path(path)
    if not p.exists():
        raise InputError(f"Image file not found: {p}")

    width = elem.get("width")
    height = elem.get("height")

    img = ImageReader(str(p))
    if width is None or height is None:
        iw, ih = img.getSize()
        if width is None and height is None:
            width, height = iw, ih
        elif width is None:
            width = iw * (height / ih)
        else:
            height = ih * (width / iw)

    c.drawImage(img, x, y, width=width, height=height, preserveAspectRatio=True)


def _draw_rect(c: Canvas, elem: dict, x: float, y: float):
    width = elem.get("width", 100)
    height = elem.get("height", 50)
    stroke_width = elem.get("stroke_width", 1)
    fill_color = elem.get("fill")
    stroke_color = elem.get("stroke", "#000000")

    c.saveState()
    c.setLineWidth(stroke_width)
    c.setStrokeColorRGB(*_hex_to_color(stroke_color))

    do_fill = 0
    if fill_color:
        c.setFillColorRGB(*_hex_to_color(fill_color))
        do_fill = 1

    c.rect(x, y, width, height, stroke=1, fill=do_fill)
    c.restoreState()


def _draw_line(c: Canvas, elem: dict, x: float, y: float):
    x2 = elem.get("x2", x)
    y2 = elem.get("y2", y)
    stroke_width = elem.get("stroke_width", 1)
    stroke_color = elem.get("stroke", "#000000")

    c.saveState()
    c.setLineWidth(stroke_width)
    c.setStrokeColorRGB(*_hex_to_color(stroke_color))
    c.line(x, y, x2, y2)
    c.restoreState()
