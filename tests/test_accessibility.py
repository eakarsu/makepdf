"""Tests for PDF accessibility features."""

import pytest

import makepdf


class TestSetLanguage:
    def test_set_language(self, sample_pdf, tmp_dir):
        out = tmp_dir / "lang.pdf"
        result = makepdf.set_language(str(sample_pdf), "en-US", str(out))
        assert result.exists()

    def test_set_german(self, sample_pdf, tmp_dir):
        out = tmp_dir / "lang.pdf"
        result = makepdf.set_language(str(sample_pdf), "de-DE", str(out))
        assert result.exists()


class TestGetLanguage:
    def test_get_language_default(self, sample_pdf):
        result = makepdf.get_language(str(sample_pdf))
        # May be None if no language is set
        assert result is None or isinstance(result, str)

    def test_get_language_after_set(self, sample_pdf, tmp_dir):
        out = tmp_dir / "lang.pdf"
        makepdf.set_language(str(sample_pdf), "fr-FR", str(out))
        result = makepdf.get_language(str(out))
        assert result == "fr-FR"


class TestSetTitleDisplay:
    def test_set_title_display(self, sample_pdf, tmp_dir):
        out = tmp_dir / "title_display.pdf"
        result = makepdf.set_title_display(str(sample_pdf), True, str(out))
        assert result.exists()


class TestCheckAccessibility:
    def test_check_accessibility(self, sample_pdf):
        report = makepdf.check_accessibility(str(sample_pdf))
        assert isinstance(report, dict)
        assert "has_language" in report
        assert "has_title" in report
        assert "is_tagged" in report
        assert "issues" in report
        assert "score" in report

    def test_check_accessible_pdf(self, sample_pdf, tmp_dir):
        # Make it more accessible: set language, then set title on the result
        with_lang = tmp_dir / "accessible.pdf"
        makepdf.set_language(str(sample_pdf), "en-US", str(with_lang))

        # Verify language was set
        lang = makepdf.get_language(str(with_lang))
        assert lang == "en-US"

        with_meta = tmp_dir / "accessible2.pdf"
        makepdf.set_metadata(str(with_lang), str(with_meta), title="Test Document")

        report = makepdf.check_accessibility(str(with_meta))
        assert report["has_title"] is True
