"""Tests for Bates numbering."""

import pytest
from pypdf import PdfReader

import makepdf


class TestAddBatesNumbers:
    def test_basic_bates(self, sample_pdf, tmp_dir):
        out = tmp_dir / "bates.pdf"
        result = makepdf.add_bates_numbers(str(sample_pdf), str(out))
        assert result.exists()

    def test_bates_with_prefix_suffix(self, sample_pdf, tmp_dir):
        out = tmp_dir / "bates.pdf"
        result = makepdf.add_bates_numbers(
            str(sample_pdf), str(out),
            prefix="DOC-", suffix="-A", start=100, digits=8
        )
        assert result.exists()

    def test_bates_positions(self, sample_pdf, tmp_dir):
        for pos in ["bottom-left", "bottom-center", "bottom-right",
                     "top-left", "top-center", "top-right"]:
            out = tmp_dir / f"bates_{pos}.pdf"
            result = makepdf.add_bates_numbers(str(sample_pdf), str(out), position=pos)
            assert result.exists(), f"Failed for position: {pos}"


class TestAddBatesToBatch:
    def test_batch_bates(self, tmp_dir):
        pdf1 = tmp_dir / "a.pdf"
        pdf2 = tmp_dir / "b.pdf"
        makepdf.from_text("Document A content", str(pdf1))
        makepdf.from_text("Document B content", str(pdf2))

        out_dir = tmp_dir / "bates_out"
        out_dir.mkdir()
        results = makepdf.add_bates_to_batch(
            [str(pdf1), str(pdf2)], str(out_dir), prefix="CASE-", start=1
        )
        assert len(results) == 2
        for r in results:
            assert r.exists()
