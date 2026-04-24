"""Shared utility functions for MakePDF."""

import tempfile
from contextlib import contextmanager
from pathlib import Path

from makepdf.config import TEMP_DIR
from makepdf.exceptions import InputError


def ensure_path(p: str | Path) -> Path:
    """Convert to Path and verify it exists."""
    path = Path(p)
    if not path.exists():
        raise InputError(f"File not found: {path}")
    return path


def ensure_pdf(p: str | Path) -> Path:
    """Convert to Path, verify it exists and is a PDF."""
    path = ensure_path(p)
    if path.suffix.lower() != ".pdf":
        raise InputError(f"Not a PDF file: {path}")
    return path


def output_path(output: str | Path | None, default_name: str) -> Path:
    """Resolve output path, using default if None."""
    if output is None:
        return Path(default_name)
    return Path(output)


@contextmanager
def temp_pdf(suffix: str = ".pdf"):
    """Context manager that yields a temporary PDF file path and cleans up."""
    fd, path = tempfile.mkstemp(suffix=suffix, dir=TEMP_DIR)
    try:
        import os
        os.close(fd)
        yield Path(path)
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass


def get_page_size(name: str = "A4"):
    """Get reportlab page size by name."""
    from reportlab.lib.pagesizes import (
        A3, A4, A5, LEGAL, LETTER,
    )
    sizes = {
        "A3": A3,
        "A4": A4,
        "A5": A5,
        "LETTER": LETTER,
        "LEGAL": LEGAL,
    }
    name = name.upper()
    if name not in sizes:
        raise InputError(f"Unknown page size: {name}. Options: {list(sizes.keys())}")
    return sizes[name]
