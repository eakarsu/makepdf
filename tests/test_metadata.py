"""Tests for PDF metadata operations."""

import pytest

import makepdf


class TestGetMetadata:
    def test_get_metadata(self, sample_pdf):
        meta = makepdf.get_metadata(str(sample_pdf))
        assert isinstance(meta, dict)
        assert "title" in meta
        assert "author" in meta
        assert "creator" in meta


class TestSetMetadata:
    def test_set_title_and_author(self, sample_pdf, tmp_dir):
        out = tmp_dir / "meta.pdf"
        result = makepdf.set_metadata(
            str(sample_pdf), str(out),
            title="Test Document", author="Test Author"
        )
        assert result.exists()

        meta = makepdf.get_metadata(str(result))
        assert meta["title"] == "Test Document"
        assert meta["author"] == "Test Author"

    def test_set_keywords(self, sample_pdf, tmp_dir):
        out = tmp_dir / "meta.pdf"
        result = makepdf.set_metadata(
            str(sample_pdf), str(out), keywords="test, pdf, makepdf"
        )
        assert result.exists()

    def test_set_all_fields(self, sample_pdf, tmp_dir):
        out = tmp_dir / "meta.pdf"
        result = makepdf.set_metadata(
            str(sample_pdf), str(out),
            title="Title", author="Author", subject="Subject",
            keywords="kw1, kw2", creator="MakePDF Test"
        )
        assert result.exists()


class TestRemoveMetadata:
    def test_remove_metadata(self, sample_pdf, tmp_dir):
        # First set some metadata
        with_meta = tmp_dir / "with_meta.pdf"
        makepdf.set_metadata(
            str(sample_pdf), str(with_meta),
            title="To Be Removed", author="Ghost"
        )

        # Then remove it
        out = tmp_dir / "no_meta.pdf"
        result = makepdf.remove_metadata(str(with_meta), str(out))
        assert result.exists()
