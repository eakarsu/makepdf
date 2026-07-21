"""Tests for irreversible PDF redaction."""

import fitz
import pytest
from PIL import Image
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

import makepdf
from makepdf.exceptions import InputError


class TestRedactArea:
    def test_redact_area_creates_pdf(self, sample_pdf, tmp_dir):
        out = tmp_dir / "redacted.pdf"
        result = makepdf.redact_area(str(sample_pdf), 0, 50, 700, 200, 30, str(out))
        assert result.exists()
        reader = PdfReader(str(result))
        assert len(reader.pages) >= 1

    def test_redact_area_custom_color(self, sample_pdf, tmp_dir):
        out = tmp_dir / "redacted.pdf"
        result = makepdf.redact_area(
            str(sample_pdf), 0, 50, 700, 200, 30, str(out), fill_color=(1, 0, 0)
        )
        assert result.exists()


class TestRedactText:
    def test_redact_text_creates_pdf(self, sample_pdf, tmp_dir):
        out = tmp_dir / "redacted.pdf"
        result = makepdf.redact_text(str(sample_pdf), "Hello", str(out))
        assert result.exists()

    def test_redact_text_removes_content(self, sample_pdf, tmp_dir):
        out = tmp_dir / "redacted.pdf"
        makepdf.redact_text(str(sample_pdf), "Hello", str(out))
        reader = PdfReader(str(out))
        assert "Hello" not in (reader.pages[0].extract_text() or "")
        assert b"Hello" not in out.read_bytes()
        assert out.read_bytes().count(b"%%EOF") == 1

    def test_redaction_scrubs_metadata_attachments_and_incremental_history(self, sample_pdf, tmp_dir):
        enriched = tmp_dir / "enriched.pdf"
        reader = PdfReader(str(sample_pdf))
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.append_pages_from_reader(reader)
        writer.add_metadata({"/Subject": "Hello recovery metadata"})
        writer.add_attachment("Hello-secret.txt", b"Hello recovery attachment")
        with enriched.open("wb") as stream:
            writer.write(stream)
        with fitz.open(enriched) as document:
            metadata = document.metadata
            metadata["keywords"] = "Hello incremental revision"
            document.set_metadata(metadata)
            document.saveIncr()
        assert enriched.read_bytes().count(b"%%EOF") >= 2

        out = tmp_dir / "sanitized.pdf"
        makepdf.redact_text(enriched, "Hello", out)
        report = makepdf.verify_redaction(out, ["Hello"])
        assert report == {
            "pages": 1,
            "embedded_files": 0,
            "incremental_revisions": 0,
            "forbidden_terms": 1,
        }

    def test_area_redaction_removes_intersecting_image_object(self, tmp_dir):
        image_path = tmp_dir / "secret.png"
        Image.new("RGB", (120, 40), "red").save(image_path)
        source = tmp_dir / "image.pdf"
        canvas = Canvas(str(source), pagesize=(300, 300))
        canvas.drawImage(str(image_path), 40, 100, width=120, height=40)
        canvas.save()

        out = tmp_dir / "image-redacted.pdf"
        makepdf.redact_area(source, 0, 40, 100, 120, 40, out)
        with fitz.open(out) as document:
            assert document[0].get_images(full=True) == []

    def test_signed_input_is_refused_for_explicit_resigning_workflow(self, tmp_dir):
        source = tmp_dir / "signed.pdf"
        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 72), "Signed secret")
        widget = fitz.Widget()
        widget.field_name = "approval-signature"
        widget.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
        widget.rect = fitz.Rect(72, 100, 240, 140)
        page.add_widget(widget)
        document.save(source)
        document.close()

        with pytest.raises(InputError, match="Signed PDFs"):
            makepdf.redact_text(source, "secret", tmp_dir / "refused.pdf")

    def test_multilingual_latin_text_is_removed(self, tmp_dir):
        source = tmp_dir / "multilingual.pdf"
        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 72), "Patient Müller confidential")
        document.save(source)
        document.close()
        out = tmp_dir / "multilingual-redacted.pdf"
        makepdf.redact_text(source, "Müller", out)
        makepdf.verify_redaction(out, ["Müller"])


class TestSearchAndRedact:
    def test_search_and_redact(self, sample_pdf, tmp_dir):
        out = tmp_dir / "redacted.pdf"
        result = makepdf.search_and_redact(
            str(sample_pdf), [r"Hello", r"test"], str(out)
        )
        assert result.exists()
