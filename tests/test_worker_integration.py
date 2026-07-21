"""Optional real native-worker execution through the durable queue."""

from __future__ import annotations

import hashlib
import shutil

import pytest
from PIL import Image, ImageDraw

import makepdf
from makepdf.web import job_registry, worker


def test_isolated_worker_completes_real_ocr_job(tmp_path, monkeypatch):
    pytest.importorskip("pytesseract")
    pytest.importorskip("pdf2image")
    if not shutil.which("tesseract") or not shutil.which("pdftoppm"):
        pytest.skip("native OCR tools are not installed")

    database = tmp_path / "service.sqlite3"
    objects = tmp_path / "objects"
    monkeypatch.setattr(job_registry, "DB_PATH", database)
    monkeypatch.setenv("MAKEPDF_JOB_DB", str(database))
    monkeypatch.setenv("MAKEPDF_OBJECT_DIR", str(objects))
    monkeypatch.setenv("MAKEPDF_TEMP_DIR", str(tmp_path / "temp"))
    job_registry.initialize()

    small = Image.new("RGB", (300, 100), "white")
    ImageDraw.Draw(small).text((20, 35), "DURABLE WORKER TEST", fill="black")
    image = small.resize((1200, 400), Image.Resampling.NEAREST)
    image_path = tmp_path / "scan.png"
    source = tmp_path / "scan.pdf"
    image.save(image_path)
    makepdf.from_images([image_path], source)
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    queued = job_registry.create_job(
        tenant_id="tenant-a",
        user_id="alice",
        kind="ocr-extract-text",
        payload={
            "source_path": str(source),
            "source_sha256": source_sha,
            "language": "eng",
            "result_dir": str(objects),
        },
        idempotency_key="native-worker-test",
        filename="ocr.txt",
    )
    claimed = job_registry.claim_next_job("integration-worker", worker.KINDS)
    assert claimed and claimed.id == queued.id
    worker._execute(claimed, "integration-worker")
    completed = job_registry.get_job(queued.id)
    assert completed.status == "complete", completed.error
    assert "DURABLE" in completed.result_path.read_text(encoding="utf-8").upper()
