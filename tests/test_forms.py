"""Tests for PDF form operations."""

import pytest

import makepdf


class TestCreateForm:
    def test_create_simple_form(self, tmp_dir):
        fields = [
            {"name": "name", "field_type": "text", "x": 100, "y": 700, "width": 200, "height": 20},
            {"name": "agree", "field_type": "checkbox", "x": 100, "y": 660, "width": 20, "height": 20},
        ]
        out = tmp_dir / "form.pdf"
        result = makepdf.create_form(fields, str(out))
        assert result.exists()


class TestListFields:
    def test_list_fields_on_form(self, tmp_dir):
        fields = [
            {"name": "email", "field_type": "text", "x": 100, "y": 700, "width": 200, "height": 20},
        ]
        form_path = tmp_dir / "form.pdf"
        makepdf.create_form(fields, str(form_path))

        listed = makepdf.list_form_fields(str(form_path))
        assert isinstance(listed, list)
        assert len(listed) >= 1
