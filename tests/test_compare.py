"""Tests for PDF comparison."""

import pytest

import makepdf


@pytest.fixture
def two_pdfs(tmp_path):
    pdf_a = tmp_path / "a.pdf"
    pdf_b = tmp_path / "b.pdf"
    makepdf.from_text("Hello World\nLine two", str(pdf_a))
    makepdf.from_text("Hello World\nLine three", str(pdf_b))
    return str(pdf_a), str(pdf_b)


@pytest.fixture
def identical_pdfs(tmp_path):
    pdf_a = tmp_path / "a.pdf"
    pdf_b = tmp_path / "b.pdf"
    makepdf.from_text("Same content here", str(pdf_a))
    makepdf.from_text("Same content here", str(pdf_b))
    return str(pdf_a), str(pdf_b)


class TestCompareText:
    def test_different_pdfs(self, two_pdfs):
        result = makepdf.compare_text(*two_pdfs)
        assert isinstance(result, dict)
        assert "identical" in result
        assert "differences" in result

    def test_identical_pdfs(self, identical_pdfs):
        result = makepdf.compare_text(*identical_pdfs)
        assert result["identical"] is True


class TestCompareMetadata:
    def test_compare_metadata(self, two_pdfs):
        result = makepdf.compare_metadata(*two_pdfs)
        assert isinstance(result, dict)
        assert "identical" in result


class TestCompareStructure:
    def test_compare_structure(self, two_pdfs):
        result = makepdf.compare_structure(*two_pdfs)
        assert isinstance(result, dict)
        assert "pages_a" in result
        assert "pages_b" in result


class TestDiffReport:
    def test_generate_diff_report(self, two_pdfs, tmp_path):
        out = tmp_path / "diff.pdf"
        result = makepdf.generate_diff_report(*two_pdfs, str(out))
        assert result.exists()
