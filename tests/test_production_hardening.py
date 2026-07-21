"""Adversarial tests for intake, identity, governance, and durable jobs."""

from __future__ import annotations

import asyncio
import io
import sqlite3
import time

import pytest
from fastapi import HTTPException
from pypdf import PdfReader, PdfWriter
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

from makepdf.web import auth, governance, intake, job_registry
from makepdf.web import app as app_module
from makepdf.web.maintenance import backup_database, verify_database


@pytest.fixture
def service_db(tmp_path, monkeypatch):
    path = tmp_path / "service.sqlite3"
    monkeypatch.setattr(job_registry, "DB_PATH", path)
    monkeypatch.setenv("MAKEPDF_API_KEY_PEPPER", "p" * 40)
    job_registry.initialize()
    auth.initialize_identity()
    return path


def test_job_queue_is_idempotent_restart_safe_retryable_and_cancellable(service_db, tmp_path):
    payload = {"source_path": "/first/path", "source_sha256": "a" * 64, "language": "eng"}
    first = job_registry.create_job(
        tenant_id="tenant-a", user_id="alice", kind="ocr-extract-text",
        payload=payload, idempotency_key="request-123", filename="result.txt",
    )
    replay = job_registry.create_job(
        tenant_id="tenant-a", user_id="alice", kind="ocr-extract-text",
        payload=payload | {"source_path": "/new/storage/path"},
        idempotency_key="request-123", filename="result.txt",
    )
    assert replay.id == first.id
    with pytest.raises(ValueError):
        job_registry.create_job(
            tenant_id="tenant-a", user_id="alice", kind="ocr-extract-text",
            payload=payload | {"source_sha256": "b" * 64}, idempotency_key="request-123",
        )

    claimed = job_registry.claim_next_job("worker-one", ["ocr-extract-text"], lease_seconds=1)
    assert claimed and claimed.id == first.id and claimed.attempts == 1
    with job_registry._connect() as db:
        db.execute("UPDATE jobs SET lease_until=? WHERE id=?", (time.time() - 1, first.id))
    assert job_registry.recover_stale_jobs() == 1
    reclaimed = job_registry.claim_next_job("worker-two", ["ocr-extract-text"])
    assert reclaimed and reclaimed.attempts == 2
    job_registry.fail_job(first.id, "worker-two", "transient", retryable=True)
    assert job_registry.get_job(first.id).status == "retry"

    other = job_registry.create_job(tenant_id="tenant-a", user_id="alice", kind="ocr-make-searchable")
    assert job_registry.request_cancel(other.id, "tenant-a", "alice")
    assert job_registry.get_job(other.id).status == "cancelled"


def test_complete_job_checksums_result_and_audit_is_immutable(service_db, tmp_path):
    job = job_registry.create_job(tenant_id="tenant-a", user_id="alice", kind="ocr-extract-text")
    claimed = job_registry.claim_next_job("worker", ["ocr-extract-text"])
    assert claimed
    result = tmp_path / "result.txt"
    result.write_text("verified result", encoding="utf-8")
    job_registry.complete_job(job.id, "worker", result, "report.txt")
    completed = job_registry.get_job(job.id, "tenant-a")
    assert completed.status == "complete"
    assert completed.extra["filename"] == "report.txt"
    events = job_registry.list_audit("tenant-a")
    assert {event["action"] for event in events} >= {"job.created", "job.completed"}
    with pytest.raises(sqlite3.IntegrityError):
        with job_registry._connect() as db:
            db.execute("UPDATE audit_events SET action='tampered'")


def test_rotating_tenant_keys_and_signed_downloads(service_db):
    key_id, raw = auth.create_api_key("tenant-a", "alice", "administrator", "primary")
    identity = auth.authenticate_api_key(raw)
    assert identity == auth.Identity("tenant-a", "alice", "administrator", key_id)
    token = auth.sign_download("job-1", identity)
    assert auth.verify_download(token, "job-1", "tenant-a") == "alice"
    assert auth.verify_download(token, "job-1", "tenant-b") is None

    replacement_id, replacement = auth.rotate_api_key(identity, key_id)
    assert auth.authenticate_api_key(raw) is None
    assert auth.authenticate_api_key(replacement).key_id == replacement_id


def test_quota_produces_idempotent_immutable_billing_statement(service_db):
    identity = auth.Identity("tenant-a", "billing-admin", "administrator", "test")
    governance.consume_quota(identity, uploaded_bytes=1234, jobs=2)
    day = time.strftime("%Y-%m-%d", time.gmtime())
    first = governance.billing_usage(identity, day)
    second = governance.billing_usage(identity, day)
    assert first["id"] == second["id"]
    assert first["usage"]["uploaded_bytes"] == 1234
    assert first["usage"]["job_count"] == 2


def test_document_access_hold_and_deletion_propagation(service_db, tmp_path):
    path = tmp_path / "document.pdf"
    path.write_bytes(b"%PDF-1.4\n%%EOF")
    owner = auth.Identity("tenant-a", "alice", "administrator", "test")
    document_id = governance.register_document(
        owner,
        intake.IntakeResult(path=path, sha256="d" * 64, size=18, pages=1),
    )
    with pytest.raises(HTTPException) as hidden:
        governance.document_for(auth.Identity("tenant-b", "alice", "administrator", "test"), document_id)
    assert hidden.value.status_code == 404

    governance.set_legal_hold(owner, document_id, True)
    with pytest.raises(HTTPException) as held:
        governance.delete_document(owner, document_id)
    assert held.value.status_code == 409 and path.exists()
    governance.set_legal_hold(owner, document_id, False)
    governance.delete_document(owner, document_id)
    assert not path.exists()


def test_streaming_intake_rejects_oversize_and_malformed_files(tmp_path, monkeypatch, sample_pdf):
    monkeypatch.setattr(intake, "TEMP_DIR", tmp_path)
    monkeypatch.setattr(intake, "MAX_UPLOAD_SIZE", 32)
    oversized = UploadFile(io.BytesIO(b"x" * 33), filename="large.bin")
    with pytest.raises(HTTPException) as too_large:
        asyncio.run(intake.save_upload(oversized, ".bin"))
    assert too_large.value.status_code == 413

    monkeypatch.setattr(intake, "MAX_UPLOAD_SIZE", 1024 * 1024)
    malformed = UploadFile(io.BytesIO(b"%PDF-1.7\nnot a pdf\n%%EOF"), filename="bad.pdf")
    with pytest.raises(HTTPException) as bad:
        asyncio.run(intake.save_upload(malformed, ".pdf"))
    assert bad.value.status_code == 422

    valid = UploadFile(io.BytesIO(sample_pdf.read_bytes()), filename="valid.pdf")
    accepted = asyncio.run(intake.save_upload(valid, ".pdf"))
    assert accepted.path.stat().st_mode & 0o777 == 0o600
    assert accepted.pages == 1


def test_intake_rejects_encrypted_pdf_and_fails_closed_without_scanner(tmp_path, monkeypatch, sample_pdf):
    monkeypatch.setattr(intake, "TEMP_DIR", tmp_path)
    reader = PdfReader(sample_pdf)
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    writer.encrypt("password")
    encrypted = io.BytesIO()
    writer.write(encrypted)
    encrypted.seek(0)
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(intake.save_upload(UploadFile(encrypted, filename="encrypted.pdf"), ".pdf"))
    assert rejected.value.status_code == 422

    monkeypatch.setattr(intake, "MALWARE_SCAN_MODE", "required")
    monkeypatch.setattr(intake.shutil, "which", lambda _command: None)
    clean = UploadFile(io.BytesIO(sample_pdf.read_bytes()), filename="clean.pdf")
    with pytest.raises(HTTPException) as unavailable:
        asyncio.run(intake.save_upload(clean, ".pdf"))
    assert unavailable.value.status_code == 503


def test_online_backup_and_restore_verify_integrity_and_audit_chain(service_db, tmp_path):
    job_registry.create_job(tenant_id="tenant-a", user_id="alice", kind="ocr-extract-text")
    backup = tmp_path / "backup.sqlite3"
    report = backup_database(backup, service_db)
    verified = verify_database(backup)
    assert report["integrity"] == verified["integrity"] == "ok"
    assert report["sha256"] == verified["sha256"]
    assert verified["audit_events"] >= 1


def test_production_quarantines_legacy_synchronous_mutations(monkeypatch):
    monkeypatch.setattr(app_module, "SERVICE_ENV", "production")
    monkeypatch.setattr(
        app_module,
        "authenticate_api_key",
        lambda _key: auth.Identity("tenant-a", "alice", "administrator", "test"),
    )
    with TestClient(app_module.create_app()) as client:
        response = client.post("/create/text", headers={"X-API-Key": "accepted"})
    assert response.status_code == 410
    assert "synchronous transformations" in response.json()["detail"]
