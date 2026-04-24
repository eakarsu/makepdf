"""Tests for PDF optimization."""

import pytest
import os

import makepdf


class TestOptimize:
    def test_optimize_pdf(self, sample_pdf, tmp_dir):
        out = tmp_dir / "optimized.pdf"
        result = makepdf.optimize(str(sample_pdf), str(out))
        assert result.exists()

    def test_optimize_with_options(self, sample_pdf, tmp_dir):
        out = tmp_dir / "optimized.pdf"
        result = makepdf.optimize(
            str(sample_pdf), str(out),
            remove_duplication=True, remove_metadata=True, compress_streams=True
        )
        assert result.exists()


class TestRemoveUnusedObjects:
    def test_remove_unused(self, sample_pdf, tmp_dir):
        out = tmp_dir / "cleaned.pdf"
        result = makepdf.remove_unused_objects(str(sample_pdf), str(out))
        assert result.exists()


class TestLinearize:
    def test_linearize(self, sample_pdf, tmp_dir):
        out = tmp_dir / "linearized.pdf"
        result = makepdf.linearize(str(sample_pdf), str(out))
        assert result.exists()


class TestOptimizationReport:
    def test_report(self, sample_pdf):
        report = makepdf.get_optimization_report(str(sample_pdf))
        assert isinstance(report, dict)
        assert "file_size" in report
        assert "page_count" in report
        assert "suggestions" in report
        assert isinstance(report["suggestions"], list)
