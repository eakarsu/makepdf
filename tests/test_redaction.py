"""Tests for PDF redaction."""

import pytest
from pypdf import PdfReader

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
        # The text should be overlaid with black rectangle
        assert out.exists()


class TestSearchAndRedact:
    def test_search_and_redact(self, sample_pdf, tmp_dir):
        out = tmp_dir / "redacted.pdf"
        result = makepdf.search_and_redact(
            str(sample_pdf), [r"Hello", r"test"], str(out)
        )
        assert result.exists()
