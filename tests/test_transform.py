"""Tests for compression, watermark, encryption, headers/footers."""

import pytest
from pypdf import PdfReader

import makepdf
from makepdf.exceptions import InputError


class TestCompress:
    def test_compress_pdf(self, sample_pdf, tmp_dir):
        out = tmp_dir / "compressed.pdf"
        result = makepdf.compress(str(sample_pdf), output=str(out))
        assert result.exists()


class TestGetPdfInfo:
    def test_info_returns_dict(self, sample_pdf):
        info = makepdf.get_pdf_info(str(sample_pdf))
        assert "page_count" in info
        assert info["page_count"] >= 1


class TestTextWatermark:
    def test_add_text_watermark(self, sample_pdf, tmp_dir):
        out = tmp_dir / "watermarked.pdf"
        result = makepdf.add_text_watermark(
            str(sample_pdf), "DRAFT", output=str(out)
        )
        assert result.exists()


class TestEncryption:
    def test_encrypt_and_decrypt(self, sample_pdf, tmp_dir):
        encrypted = tmp_dir / "encrypted.pdf"
        result = makepdf.encrypt(str(sample_pdf), str(encrypted), user_password="pass123")
        assert result.exists()
        assert makepdf.is_encrypted(str(encrypted))

        decrypted = tmp_dir / "decrypted.pdf"
        result2 = makepdf.decrypt(str(encrypted), str(decrypted), password="pass123")
        assert result2.exists()

        text = makepdf.extract_text(str(decrypted))
        assert "Hello World" in text


class TestHeadersFooters:
    def test_add_headers_footers(self, sample_pdf, tmp_dir):
        out = tmp_dir / "with_hf.pdf"
        result = makepdf.add_headers_footers(
            str(sample_pdf),
            output=str(out),
            header_center="Test Doc",
            footer_center="Page {page}",
        )
        assert result.exists()
