"""Tests for text markup annotations."""

import pytest
from pypdf import PdfReader

import makepdf


class TestHighlightArea:
    def test_highlight_area(self, sample_pdf, tmp_dir):
        out = tmp_dir / "highlighted.pdf"
        result = makepdf.highlight_area(str(sample_pdf), 0, 72, 700, 200, 20, str(out))
        assert result.exists()

    def test_highlight_custom_color(self, sample_pdf, tmp_dir):
        out = tmp_dir / "highlighted.pdf"
        result = makepdf.highlight_area(
            str(sample_pdf), 0, 72, 700, 200, 20, str(out), color=(0, 1, 0)
        )
        assert result.exists()


class TestUnderlineArea:
    def test_underline_area(self, sample_pdf, tmp_dir):
        out = tmp_dir / "underlined.pdf"
        result = makepdf.underline_area(str(sample_pdf), 0, 72, 700, 200, 20, str(out))
        assert result.exists()


class TestStrikethroughArea:
    def test_strikethrough_area(self, sample_pdf, tmp_dir):
        out = tmp_dir / "strikethrough.pdf"
        result = makepdf.strikethrough_area(str(sample_pdf), 0, 72, 700, 200, 20, str(out))
        assert result.exists()


class TestAddStickyNote:
    def test_add_sticky_note(self, sample_pdf, tmp_dir):
        out = tmp_dir / "noted.pdf"
        result = makepdf.add_sticky_note(
            str(sample_pdf), 0, 200, 700, "This is a note", str(out)
        )
        assert result.exists()

    def test_sticky_note_custom_icon(self, sample_pdf, tmp_dir):
        out = tmp_dir / "noted.pdf"
        result = makepdf.add_sticky_note(
            str(sample_pdf), 0, 200, 700, "Key note", str(out),
            color=(1, 0, 0), icon="Key"
        )
        assert result.exists()


class TestAddTextComment:
    def test_add_text_comment(self, sample_pdf, tmp_dir):
        out = tmp_dir / "commented.pdf"
        result = makepdf.add_text_comment(
            str(sample_pdf), 0, 72, 600, 200, 50, "This is a comment", str(out)
        )
        assert result.exists()
