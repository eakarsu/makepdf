"""Tests for PDF stamps."""

import pytest
from PIL import Image

import makepdf
from makepdf.exceptions import InputError


class TestAddStamp:
    def test_add_approved_stamp(self, sample_pdf, tmp_dir):
        out = tmp_dir / "stamped.pdf"
        result = makepdf.add_stamp(str(sample_pdf), "APPROVED", str(out))
        assert result.exists()

    def test_add_draft_stamp(self, sample_pdf, tmp_dir):
        out = tmp_dir / "stamped.pdf"
        result = makepdf.add_stamp(str(sample_pdf), "DRAFT", str(out))
        assert result.exists()

    def test_add_confidential_stamp(self, sample_pdf, tmp_dir):
        out = tmp_dir / "stamped.pdf"
        result = makepdf.add_stamp(
            str(sample_pdf), "CONFIDENTIAL", str(out), position="top-right", opacity=0.7
        )
        assert result.exists()

    def test_all_stamp_types(self, sample_pdf, tmp_dir):
        for stype in ["APPROVED", "DRAFT", "CONFIDENTIAL", "FINAL", "VOID",
                       "FOR REVIEW", "PRELIMINARY", "EXPIRED", "COPY", "NOT APPROVED"]:
            out = tmp_dir / f"stamp_{stype.replace(' ', '_')}.pdf"
            result = makepdf.add_stamp(str(sample_pdf), stype, str(out))
            assert result.exists(), f"Failed for stamp type: {stype}"


class TestAddCustomStamp:
    def test_custom_stamp(self, sample_pdf, tmp_dir):
        out = tmp_dir / "custom_stamp.pdf"
        result = makepdf.add_custom_stamp(
            str(sample_pdf), "INTERNAL USE ONLY", str(out),
            font_size=24, color=(0.5, 0, 0.5)
        )
        assert result.exists()


class TestAddImageStamp:
    def test_image_stamp(self, sample_pdf, tmp_dir):
        img_path = tmp_dir / "logo.png"
        img = Image.new("RGBA", (100, 50), (0, 0, 255, 128))
        img.save(str(img_path))

        out = tmp_dir / "img_stamp.pdf"
        result = makepdf.add_image_stamp(str(sample_pdf), str(img_path), str(out))
        assert result.exists()
