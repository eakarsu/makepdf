"""Tests for PDF page cropping and resizing."""

import pytest
from pypdf import PdfReader

import makepdf
from makepdf.exceptions import InputError


class TestCropPages:
    def test_crop_all_pages(self, sample_pdf, tmp_dir):
        out = tmp_dir / "cropped.pdf"
        result = makepdf.crop_pages(str(sample_pdf), 36, 36, 36, 36, str(out))
        assert result.exists()
        reader = PdfReader(str(result))
        assert len(reader.pages) >= 1

    def test_crop_specific_pages(self, sample_pdf, tmp_dir):
        out = tmp_dir / "cropped.pdf"
        result = makepdf.crop_pages(str(sample_pdf), 10, 10, 10, 10, str(out), pages=[1])
        assert result.exists()


class TestResizePages:
    def test_resize_pages(self, sample_pdf, tmp_dir):
        out = tmp_dir / "resized.pdf"
        result = makepdf.resize_pages(str(sample_pdf), 400, 600, str(out))
        assert result.exists()


class TestTrimMargins:
    def test_trim_margins(self, sample_pdf, tmp_dir):
        out = tmp_dir / "trimmed.pdf"
        result = makepdf.trim_margins(str(sample_pdf), 20, str(out))
        assert result.exists()


class TestSetPageBoxes:
    def test_set_cropbox(self, sample_pdf, tmp_dir):
        out = tmp_dir / "boxed.pdf"
        result = makepdf.set_page_boxes(
            str(sample_pdf), "CropBox", 50, 50, 500, 700, str(out)
        )
        assert result.exists()
