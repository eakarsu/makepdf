"""Tests for PDF creation."""

import pytest
from pathlib import Path
from pypdf import PdfReader

import makepdf
from makepdf.exceptions import InputError


class TestFromText:
    def test_creates_pdf(self, tmp_dir):
        out = tmp_dir / "out.pdf"
        result = makepdf.from_text("Hello World", str(out))
        assert result.exists()
        reader = PdfReader(str(result))
        assert len(reader.pages) >= 1

    def test_text_is_in_pdf(self, tmp_dir):
        out = tmp_dir / "out.pdf"
        makepdf.from_text("UniqueTestString123", str(out))
        reader = PdfReader(str(out))
        text = reader.pages[0].extract_text()
        assert "UniqueTestString123" in text

    def test_empty_text_raises(self, tmp_dir):
        with pytest.raises(InputError):
            makepdf.from_text("", str(tmp_dir / "out.pdf"))

    def test_custom_font_and_size(self, tmp_dir):
        out = tmp_dir / "out.pdf"
        result = makepdf.from_text("Test", str(out), font="Courier", font_size=20)
        assert result.exists()

    def test_page_sizes(self, tmp_dir):
        for size in ["A4", "letter", "legal"]:
            out = tmp_dir / f"out_{size}.pdf"
            result = makepdf.from_text("Test", str(out), page_size=size)
            assert result.exists()


class TestFromImages:
    def test_creates_pdf_from_images(self, tmp_dir):
        from PIL import Image

        # Create test images
        imgs = []
        for i in range(3):
            img_path = tmp_dir / f"img_{i}.png"
            img = Image.new("RGB", (200, 200), color=(i * 80, 100, 150))
            img.save(str(img_path))
            imgs.append(str(img_path))

        out = tmp_dir / "from_images.pdf"
        result = makepdf.from_images(imgs, str(out))
        assert result.exists()
        reader = PdfReader(str(result))
        assert len(reader.pages) == 3
