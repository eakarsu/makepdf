"""PDF forms module – create, fill, and extract fillable PDF form fields."""

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas as canvas_module

from makepdf.exceptions import InputError
from makepdf.utils import ensure_pdf, get_page_size, output_path


# ---------------------------------------------------------------------------
# 1. Create a PDF with fillable form fields
# ---------------------------------------------------------------------------

def create_form(
    fields: list[dict],
    output: str | Path,
    page_size: str = "A4",
) -> Path:
    """Create a PDF containing fillable form fields.

    Parameters
    ----------
    fields : list[dict]
        Each dict must contain at least ``name``, ``field_type``, ``x``, ``y``,
        ``width``, ``height``.  Optional keys: ``options`` (list of str, for
        dropdown / radio), ``label`` (str shown next to the field), ``default``
        (initial value).
    output : str | Path
        Destination file path for the generated PDF.
    page_size : str
        Page size name understood by :func:`makepdf.utils.get_page_size`
        (default ``"A4"``).

    Returns
    -------
    Path
        The resolved output file path.
    """
    if not fields:
        raise InputError("fields list must not be empty")

    out = output_path(output, "form.pdf")
    size = get_page_size(page_size)

    c = canvas_module.Canvas(str(out), pagesize=size)

    for field in fields:
        # Required keys ---------------------------------------------------
        for key in ("name", "field_type", "x", "y", "width", "height"):
            if key not in field:
                raise InputError(f"Form field missing required key: {key!r}")

        name = field["name"]
        ftype = field["field_type"]
        x = float(field["x"])
        y = float(field["y"])
        w = float(field["width"])
        h = float(field["height"])

        label = field.get("label")
        default = field.get("default", "")
        options = field.get("options", [])

        # Draw optional label to the left of the field --------------------
        if label:
            c.setFont("Helvetica", 10)
            c.drawString(x - 5 - c.stringWidth(label, "Helvetica", 10), y + 3, label)

        # Create the appropriate AcroForm widget --------------------------
        if ftype == "text":
            c.acroForm.textfield(
                name=name,
                x=x,
                y=y,
                width=w,
                height=h,
                value=str(default),
                fontSize=10,
            )

        elif ftype == "checkbox":
            checked = bool(default) if default != "" else False
            c.acroForm.checkbox(
                name=name,
                x=x,
                y=y,
                size=h,
                checked=checked,
            )

        elif ftype == "dropdown":
            if not options:
                raise InputError(
                    f"Dropdown field {name!r} requires a non-empty 'options' list"
                )
            c.acroForm.choice(
                name=name,
                x=x,
                y=y,
                width=w,
                height=h,
                options=options,
                value=str(default) if default else options[0],
                fontSize=10,
            )

        elif ftype == "radio":
            if not options:
                raise InputError(
                    f"Radio field {name!r} requires a non-empty 'options' list"
                )
            value = str(default) if default else options[0]
            c.acroForm.radio(
                name=name,
                x=x,
                y=y,
                size=h,
                value=value,
            )

        else:
            raise InputError(
                f"Unknown field_type {ftype!r}. "
                "Supported types: text, checkbox, dropdown, radio"
            )

    c.showPage()
    c.save()
    return out


# ---------------------------------------------------------------------------
# 2. Fill form fields in an existing PDF
# ---------------------------------------------------------------------------

def fill_form(
    input_pdf: str | Path,
    data: dict[str, str],
    output: str | Path,
) -> Path:
    """Fill form fields in *input_pdf* with values from *data*.

    Parameters
    ----------
    input_pdf : str | Path
        Path to the source PDF that contains AcroForm fields.
    data : dict[str, str]
        Mapping of field names to the values to fill in.
    output : str | Path
        Destination path for the filled PDF.

    Returns
    -------
    Path
        The resolved output file path.
    """
    src = ensure_pdf(input_pdf)
    out = output_path(output, "filled_form.pdf")

    reader = PdfReader(str(src))
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)

    # Copy AcroForm from reader so fields are preserved
    if "/AcroForm" in reader.trailer["/Root"]:
        writer._root_object.update(
            {"/AcroForm": reader.trailer["/Root"]["/AcroForm"]}
        )

    writer.update_page_form_field_values(writer.pages[0], data)

    with open(out, "wb") as fp:
        writer.write(fp)

    return out


# ---------------------------------------------------------------------------
# 3. Extract form field names and current values
# ---------------------------------------------------------------------------

def extract_form_data(input_pdf: str | Path) -> dict:
    """Extract all form field names and their current values.

    Parameters
    ----------
    input_pdf : str | Path
        Path to a PDF containing form fields.

    Returns
    -------
    dict
        Mapping of field names to their string values.  Fields without a
        value are mapped to an empty string.
    """
    src = ensure_pdf(input_pdf)
    reader = PdfReader(str(src))

    # get_form_text_fields returns only text fields; get_fields returns all.
    result: dict[str, str] = {}

    # Start with text-field helper (returns {name: value} or None)
    text_fields = reader.get_form_text_fields()
    if text_fields:
        for name, value in text_fields.items():
            result[name] = value if value is not None else ""

    # Merge in any remaining fields from get_fields (checkboxes, etc.)
    all_fields = reader.get_fields()
    if all_fields:
        for name, field_obj in all_fields.items():
            if name not in result:
                value = field_obj.get("/V", "")
                if hasattr(value, "get_object"):
                    value = str(value.get_object())
                result[name] = str(value) if value is not None else ""

    return result


# ---------------------------------------------------------------------------
# 4. List form field names and types
# ---------------------------------------------------------------------------

_FIELD_TYPE_MAP = {
    "/Tx": "text",
    "/Ch": "dropdown",
    "/Btn": "button",  # checkbox or radio
    "/Sig": "signature",
}


def list_form_fields(input_pdf: str | Path) -> list[dict]:
    """List all form field names, types, and current values.

    Parameters
    ----------
    input_pdf : str | Path
        Path to a PDF containing form fields.

    Returns
    -------
    list[dict]
        Each dict contains ``name`` (str), ``type`` (str), and ``value``
        (str).  The type is a human-readable label derived from the PDF
        field-type flag (``/FT``).
    """
    src = ensure_pdf(input_pdf)
    reader = PdfReader(str(src))

    all_fields = reader.get_fields()
    if not all_fields:
        return []

    result: list[dict] = []
    for name, field_obj in all_fields.items():
        ft = field_obj.get("/FT", "")
        field_type = _FIELD_TYPE_MAP.get(str(ft), str(ft))

        # Distinguish checkbox vs radio for /Btn fields
        if field_type == "button":
            flags = int(field_obj.get("/Ff", 0))
            # Bit 16 (0-indexed 15) of field flags indicates radio button
            if flags & (1 << 15):
                field_type = "radio"
            else:
                field_type = "checkbox"

        value = field_obj.get("/V", "")
        if hasattr(value, "get_object"):
            value = str(value.get_object())
        value = str(value) if value is not None else ""

        result.append({"name": name, "type": field_type, "value": value})

    return result
