"""Tests for PDF page labels."""

import pytest

import makepdf


class TestSetPageLabels:
    def test_set_decimal_labels(self, sample_pdf, tmp_dir):
        out = tmp_dir / "labeled.pdf"
        labels = [{"start_page": 0, "style": "decimal", "prefix": "", "first_number": 1}]
        result = makepdf.set_page_labels(str(sample_pdf), labels, str(out))
        assert result.exists()

    def test_set_roman_labels(self, sample_pdf, tmp_dir):
        out = tmp_dir / "labeled.pdf"
        labels = [{"start_page": 0, "style": "roman_lower"}]
        result = makepdf.set_page_labels(str(sample_pdf), labels, str(out))
        assert result.exists()

    def test_set_prefixed_labels(self, sample_pdf, tmp_dir):
        out = tmp_dir / "labeled.pdf"
        labels = [{"start_page": 0, "style": "decimal", "prefix": "A-", "first_number": 1}]
        result = makepdf.set_page_labels(str(sample_pdf), labels, str(out))
        assert result.exists()


class TestGetPageLabels:
    def test_get_page_labels_default(self, sample_pdf):
        result = makepdf.get_page_labels(str(sample_pdf))
        assert isinstance(result, list)

    def test_roundtrip(self, sample_pdf, tmp_dir):
        labels = [{"start_page": 0, "style": "decimal", "prefix": "P-", "first_number": 1}]
        out = tmp_dir / "labeled.pdf"
        makepdf.set_page_labels(str(sample_pdf), labels, str(out))
        result = makepdf.get_page_labels(str(out))
        assert isinstance(result, list)
        assert len(result) >= 1
