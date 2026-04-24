"""Tests for merge, split, and page operations."""

import pytest
from pathlib import Path
from pypdf import PdfReader

import makepdf
from makepdf.exceptions import InputError


class TestMerge:
    def test_merge_two_pdfs(self, tmp_dir):
        pdf1 = tmp_dir / "a.pdf"
        pdf2 = tmp_dir / "b.pdf"
        makepdf.from_text("File A", str(pdf1))
        makepdf.from_text("File B", str(pdf2))

        out = tmp_dir / "merged.pdf"
        result = makepdf.merge([str(pdf1), str(pdf2)], str(out))
        assert result.exists()
        reader = PdfReader(str(result))
        assert len(reader.pages) == 2

    def test_merge_empty_list_raises(self, tmp_dir):
        with pytest.raises(InputError):
            makepdf.merge([])


class TestSplit:
    def test_split_pdf(self, sample_pdf, tmp_dir):
        results = makepdf.split(str(sample_pdf), [(1, 1)], str(tmp_dir))
        assert len(results) == 1
        assert results[0].exists()

    def test_split_invalid_range(self, sample_pdf, tmp_dir):
        with pytest.raises(InputError):
            makepdf.split(str(sample_pdf), [(0, 1)], str(tmp_dir))


class TestExtractPages:
    def test_extract_single_page(self, sample_pdf, tmp_dir):
        out = tmp_dir / "extracted.pdf"
        result = makepdf.extract_pages(str(sample_pdf), [1], str(out))
        assert result.exists()
        reader = PdfReader(str(result))
        assert len(reader.pages) == 1


class TestRotate:
    def test_rotate_pages(self, sample_pdf, tmp_dir):
        out = tmp_dir / "rotated.pdf"
        result = makepdf.rotate_pages(str(sample_pdf), [1], 90, output=str(out))
        assert result.exists()
