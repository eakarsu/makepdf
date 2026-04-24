"""Tests for PDF editing (add text, images)."""

import pytest
from pathlib import Path
from PIL import Image

import makepdf


class TestAddText:
    def test_add_text_to_pdf(self, sample_pdf, tmp_dir):
        out = tmp_dir / "edited.pdf"
        result = makepdf.add_text(
            str(sample_pdf), 0, 100, 500, "Overlay text", str(out)
        )
        assert result.exists()


class TestAddImage:
    def test_add_image_to_pdf(self, sample_pdf, tmp_dir):
        img_path = tmp_dir / "stamp.png"
        img = Image.new("RGBA", (100, 50), (255, 0, 0, 128))
        img.save(str(img_path))

        out = tmp_dir / "with_image.pdf"
        result = makepdf.add_image(
            str(sample_pdf), 0, 100, 400, str(img_path), str(out)
        )
        assert result.exists()
