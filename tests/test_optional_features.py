"""Checks for optional native/HTML installations in the CI feature matrix."""

import shutil

import pytest

from makepdf.core.creator import from_html
from makepdf.exceptions import InputError


def test_html_renderer_is_installed_and_cannot_fetch_external_resources(tmp_path):
    pytest.importorskip("weasyprint")
    with pytest.raises(InputError, match="resource URLs"):
        from_html('<img src="https://169.254.169.254/latest/meta-data/">', tmp_path / "ssrf.pdf")
    result = from_html("<h1>Offline content</h1>", tmp_path / "offline.pdf")
    assert result.is_file()


def test_optional_native_tools_are_present():
    assert shutil.which("pdftoppm")
    assert shutil.which("tesseract")
