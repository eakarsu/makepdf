"""Constrained parser entry point for attacker-controlled files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from makepdf.config import (
    MAX_DECOMPRESSION_RATIO,
    MAX_PDF_OBJECTS,
    MAX_PDF_PAGES,
    MAX_RENDER_PIXELS,
)


def probe_pdf(path: Path, file_size: int) -> dict[str, int]:
    import fitz

    with fitz.open(str(path)) as document:
        if not document.is_pdf or document.needs_pass:
            raise ValueError("encrypted or non-PDF input")
        if document.page_count < 1 or document.page_count > MAX_PDF_PAGES:
            raise ValueError(f"page count must be between 1 and {MAX_PDF_PAGES}")
        if document.xref_length() > MAX_PDF_OBJECTS:
            raise ValueError(f"object count exceeds {MAX_PDF_OBJECTS}")
        expanded_pixels = 0
        for page in document:
            for image in page.get_images(full=True):
                width, height = int(image[2]), int(image[3])
                if width <= 0 or height <= 0:
                    raise ValueError("invalid embedded image dimensions")
                expanded_pixels += width * height * 4
                if expanded_pixels > MAX_RENDER_PIXELS:
                    raise ValueError("embedded image expansion exceeds the pixel budget")
        if file_size and expanded_pixels / file_size > MAX_DECOMPRESSION_RATIO:
            raise ValueError("embedded image decompression ratio exceeds the budget")
        return {"pages": document.page_count}


def probe_image(path: Path) -> dict[str, int]:
    from PIL import Image

    with Image.open(path) as image:
        width, height = image.size
        if width <= 0 or height <= 0 or width * height > MAX_RENDER_PIXELS:
            raise ValueError("image dimensions exceed the pixel budget")
        image.verify()
        return {"width": width, "height": height}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("pdf", "image"))
    parser.add_argument("path", type=Path)
    parser.add_argument("--size", type=int, default=0)
    arguments = parser.parse_args()
    result = (
        probe_pdf(arguments.path, arguments.size)
        if arguments.kind == "pdf"
        else probe_image(arguments.path)
    )
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
