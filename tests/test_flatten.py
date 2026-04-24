"""Tests for PDF flattening."""

import pytest

import makepdf


class TestFlattenForms:
    def test_flatten_forms(self, sample_pdf, tmp_dir):
        out = tmp_dir / "flattened.pdf"
        result = makepdf.flatten_forms(str(sample_pdf), str(out))
        assert result.exists()

    def test_flatten_form_with_fields(self, tmp_dir):
        # Create a form first, then flatten it
        fields = [
            {"name": "name", "field_type": "text", "x": 100, "y": 700, "width": 200, "height": 20},
        ]
        form_path = tmp_dir / "form.pdf"
        makepdf.create_form(fields, str(form_path))

        out = tmp_dir / "flat.pdf"
        result = makepdf.flatten_forms(str(form_path), str(out))
        assert result.exists()


class TestFlattenAnnotations:
    def test_flatten_annotations(self, sample_pdf, tmp_dir):
        out = tmp_dir / "flattened.pdf"
        result = makepdf.flatten_annotations(str(sample_pdf), str(out))
        assert result.exists()


class TestFlattenAll:
    def test_flatten_all(self, sample_pdf, tmp_dir):
        out = tmp_dir / "flattened.pdf"
        result = makepdf.flatten_all(str(sample_pdf), str(out))
        assert result.exists()
