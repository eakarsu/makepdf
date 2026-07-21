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
try:
    TEMP_DIR.chmod(0o700)
except OSError:
    pass

MAX_UPLOAD_SIZE = int(os.getenv("MAKEPDF_MAX_UPLOAD_MB", "100")) * 1024 * 1024
MAX_PDF_PAGES = int(os.getenv("MAKEPDF_MAX_PDF_PAGES", "500"))
MAX_PDF_OBJECTS = int(os.getenv("MAKEPDF_MAX_PDF_OBJECTS", "100000"))
MAX_RENDER_PIXELS = int(os.getenv("MAKEPDF_MAX_RENDER_MPIXELS", "250")) * 1_000_000
MAX_DECOMPRESSION_RATIO = int(os.getenv("MAKEPDF_MAX_DECOMPRESSION_RATIO", "200"))
MAX_JOB_SECONDS = int(os.getenv("MAKEPDF_MAX_JOB_SECONDS", "900"))
JOB_RESULT_TTL_SECONDS = int(os.getenv("MAKEPDF_RESULT_TTL_SECONDS", "86400"))
JOB_MAX_ATTEMPTS = int(os.getenv("MAKEPDF_JOB_MAX_ATTEMPTS", "3"))
SERVICE_ENV = os.getenv("MAKEPDF_ENV", "development").strip().lower()

DATA_DIR = Path(
    os.getenv(
        "MAKEPDF_DATA_DIR",
        str(Path.home() / ".local" / "share" / "makepdf"),
    )
).expanduser()
JOB_DB_PATH = Path(os.getenv("MAKEPDF_JOB_DB", str(DATA_DIR / "service.sqlite3")))
OBJECT_DIR = Path(os.getenv("MAKEPDF_OBJECT_DIR", str(DATA_DIR / "objects")))
MALWARE_SCAN_MODE = os.getenv(
    "MAKEPDF_MALWARE_SCAN_MODE",
    "required" if SERVICE_ENV == "production" else "disabled",
).strip().lower()
CLAMAV_COMMAND = os.getenv("MAKEPDF_CLAMAV_COMMAND", "clamdscan")

OCR_LANGUAGE = os.getenv("MAKEPDF_OCR_LANG", "eng")

WEB_HOST = os.getenv("MAKEPDF_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("MAKEPDF_PORT", "8000"))
