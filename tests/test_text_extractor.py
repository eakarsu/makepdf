"""Tests for text extraction and search."""

import pytest

import makepdf
from makepdf.exceptions import InputError


class TestExtractText:
    def test_extract_all(self, sample_pdf):
        text = makepdf.extract_text(str(sample_pdf))
        assert "Hello World" in text

    def test_extract_specific_page(self, sample_pdf):
        text = makepdf.extract_text(str(sample_pdf), pages=[1])
        assert isinstance(text, str)

    def test_invalid_page_raises(self, sample_pdf):
        with pytest.raises(InputError):
            makepdf.extract_text(str(sample_pdf), pages=[999])


class TestExtractByPage:
    def test_returns_dict(self, sample_pdf):
        result = makepdf.extract_text_by_page(str(sample_pdf))
        assert isinstance(result, dict)
        assert 1 in result


class TestSearch:
    def test_finds_text(self, sample_pdf):
        results = makepdf.search_text(str(sample_pdf), "Hello")
        assert len(results) >= 1
        assert results[0]["page"] == 1

    def test_empty_query_raises(self, sample_pdf):
        with pytest.raises(InputError):
            makepdf.search_text(str(sample_pdf), "")

    def test_no_match_returns_empty(self, sample_pdf):
        results = makepdf.search_text(str(sample_pdf), "ZZZZNOTFOUND")
        assert results == []
