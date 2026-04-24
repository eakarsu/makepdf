"""Global configuration for MakePDF."""

import os
import tempfile
from pathlib import Path


DEFAULT_FONT = "Helvetica"
DEFAULT_FONT_SIZE = 12
DEFAULT_DPI = 200
DEFAULT_PAGE_SIZE = "A4"
DEFAULT_MARGIN = 72  # 1 inch in points

TEMP_DIR = Path(os.getenv("MAKEPDF_TEMP_DIR", tempfile.gettempdir())) / "makepdf"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_SIZE = int(os.getenv("MAKEPDF_MAX_UPLOAD_MB", "100")) * 1024 * 1024

OCR_LANGUAGE = os.getenv("MAKEPDF_OCR_LANG", "eng")

WEB_HOST = os.getenv("MAKEPDF_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("MAKEPDF_PORT", "8000"))
