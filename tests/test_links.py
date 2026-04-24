"""Tests for PDF hyperlinks."""

import pytest

import makepdf


class TestAddLink:
    def test_add_url_link(self, sample_pdf, tmp_dir):
        out = tmp_dir / "linked.pdf"
        result = makepdf.add_link(
            str(sample_pdf), 0, 100, 700, 200, 20,
            "https://example.com", str(out)
        )
        assert result.exists()

    def test_add_link_with_border(self, sample_pdf, tmp_dir):
        out = tmp_dir / "linked.pdf"
        result = makepdf.add_link(
            str(sample_pdf), 0, 100, 700, 200, 20,
            "https://example.com", str(out), border=True
        )
        assert result.exists()


class TestAddInternalLink:
    def test_add_internal_link(self, tmp_dir):
        # Create two single-page PDFs and merge them
        p1 = tmp_dir / "p1.pdf"
        p2 = tmp_dir / "p2.pdf"
        makepdf.from_text("Page 1 content", str(p1))
        makepdf.from_text("Page 2 content", str(p2))
        pdf_path = tmp_dir / "multi.pdf"
        makepdf.merge([str(p1), str(p2)], str(pdf_path))

        out = tmp_dir / "internal_link.pdf"
        result = makepdf.add_internal_link(
            str(pdf_path), 0, 100, 700, 200, 20, 1, str(out)
        )
        assert result.exists()


class TestExtractLinks:
    def test_extract_links_empty(self, sample_pdf):
        result = makepdf.extract_links(str(sample_pdf))
        assert isinstance(result, list)

    def test_extract_links_after_adding(self, sample_pdf, tmp_dir):
        with_link = tmp_dir / "linked.pdf"
        makepdf.add_link(
            str(sample_pdf), 0, 100, 700, 200, 20,
            "https://example.com", str(with_link)
        )
        result = makepdf.extract_links(str(with_link))
        assert isinstance(result, list)
        assert len(result) >= 1
