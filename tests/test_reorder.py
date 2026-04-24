"""Tests for page reordering."""

import pytest
from pypdf import PdfReader

import makepdf
from makepdf.exceptions import InputError


class TestReorderPages:
    def test_reorder_reverses(self, tmp_dir):
        # Create a 2-page PDF
        pdf1 = tmp_dir / "a.pdf"
        pdf2 = tmp_dir / "b.pdf"
        makepdf.from_text("Page A", str(pdf1))
        makepdf.from_text("Page B", str(pdf2))
        merged = tmp_dir / "merged.pdf"
        makepdf.merge([str(pdf1), str(pdf2)], str(merged))

        out = tmp_dir / "reordered.pdf"
        result = makepdf.reorder_pages(str(merged), [2, 1], str(out))
        assert result.exists()
        reader = PdfReader(str(result))
        assert len(reader.pages) == 2

    def test_reorder_duplicate_pages(self, sample_pdf, tmp_dir):
        out = tmp_dir / "reordered.pdf"
        result = makepdf.reorder_pages(str(sample_pdf), [1, 1, 1], str(out))
        assert result.exists()
        reader = PdfReader(str(result))
        assert len(reader.pages) == 3

    def test_reorder_empty_raises(self, sample_pdf, tmp_dir):
        with pytest.raises(InputError):
            makepdf.reorder_pages(str(sample_pdf), [], str(tmp_dir / "out.pdf"))

    def test_reorder_invalid_page(self, sample_pdf, tmp_dir):
        with pytest.raises(InputError):
            makepdf.reorder_pages(str(sample_pdf), [999], str(tmp_dir / "out.pdf"))
