"""Shared fixtures for MakePDF tests."""

import pytest
from pathlib import Path

import makepdf


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temporary directory."""
    return tmp_path


@pytest.fixture
def sample_pdf(tmp_path):
    """Create a simple single-page PDF for testing."""
    out = tmp_path / "sample.pdf"
    makepdf.from_text("Hello World\nThis is a test PDF.", str(out))
    return out


@pytest.fixture
def multi_page_pdf(tmp_path):
    """Create a multi-page PDF for testing."""
    out = tmp_path / "multi.pdf"
    text = "\n".join([f"Page {i} content. " * 50 for i in range(1, 6)])
    makepdf.from_text(text, str(out))
    return out
