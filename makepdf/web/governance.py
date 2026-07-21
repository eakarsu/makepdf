"""Document ownership, retention, legal hold, quota, and deletion propagation."""

from __future__ import annotations

import os
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from makepdf.web.auth import Identity, initialize_identity
from makepdf.web.intake import IntakeResult, secure_unlink
from makepdf.web.job_registry import _connect, append_audit, request_cancel


def consume_quota(identity: Identity, *, uploaded_bytes: int = 0, jobs: int = 0) -> None:
    max_requests = int(os.getenv("MAKEPDF_DAILY_REQUEST_QUOTA", "1000"))
    max_bytes = int(os.getenv("MAKEPDF_DAILY_UPLOAD_MB", "10000")) * 1024 * 1024
    max_jobs = int(os.getenv("MAKEPDF_DAILY_JOB_QUOTA", "500"))
    day = datetime.now(timezone.utc).date().isoformat()
    initialize_identity()
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT INTO usage_daily(tenant_id,day,request_count,uploaded_bytes,job_count) VALUES(?,?,1,?,?) "
            "ON CONFLICT(tenant_id,day) DO UPDATE SET request_count=request_count+1,"
            "uploaded_bytes=uploaded_bytes+excluded.uploaded_bytes,job_count=job_count+excluded.job_count",
            (identity.tenant_id, day, uploaded_bytes, jobs),
        )
        row = db.execute(
            "SELECT * FROM usage_daily WHERE tenant_id=? AND day=?",
            (identity.tenant_id, day),
        ).fetchone()
        if row["request_count"] > max_requests or row["uploaded_bytes"] > max_bytes or row["job_count"] > max_jobs:
            db.rollback()
            raise HTTPException(status_code=429, detail="Tenant daily quota exceeded.")
        db.commit()


def billing_usage(identity: Identity, day: str) -> dict:
    """Create an immutable, digest-addressed daily usage statement."""
    if not identity.is_admin:
        raise HTTPException(status_code=403, detail="Administrator role is required.")
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="day must use YYYY-MM-DD") from exc
    initialize_identity()
    with _connect() as db:
        usage = db.execute(
            "SELECT request_count,uploaded_bytes,job_count FROM usage_daily WHERE tenant_id=? AND day=?",
            (identity.tenant_id, day),
        ).fetchone()
        statement = {
            "tenant_id": identity.tenant_id,
            "day": day,
            "request_count": int(usage["request_count"]) if usage else 0,
            "uploaded_bytes": int(usage["uploaded_bytes"]) if usage else 0,
            "job_count": int(usage["job_count"]) if usage else 0,
        }
        encoded = json.dumps(statement, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        export_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO billing_exports(id,tenant_id,day,usage_json,usage_sha256,created_by,created_at) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(tenant_id,day) DO NOTHING",
            (export_id, identity.tenant_id, day, encoded, digest, identity.user_id, time.time()),
        )
        row = db.execute(
            "SELECT id,usage_json,usage_sha256,created_at FROM billing_exports WHERE tenant_id=? AND day=?",
            (identity.tenant_id, day),
        ).fetchone()
    append_audit(identity.tenant_id, identity.user_id, "billing.usage.exported", "billing_export", row["id"], {"day": day, "sha256": row["usage_sha256"]})
    return {
        "id": row["id"],
        "usage": json.loads(row["usage_json"]),
        "sha256": row["usage_sha256"],
        "created_at": row["created_at"],
    }


def register_document(identity: Identity, intake: IntakeResult, retention_days: int = 7) -> str:
    initialize_identity()
    document_id = str(uuid.uuid4())
    now = time.time()
    with _connect() as db:
        db.execute(
            "INSERT INTO documents(id,tenant_id,owner_user_id,source_path,source_sha256,size_bytes,"
            "page_count,status,retention_until,created_at) VALUES(?,?,?,?,?,?,?,'active',?,?)",
            (
                document_id, identity.tenant_id, identity.user_id, str(intake.path), intake.sha256,
                intake.size, intake.pages, now + max(1, retention_days) * 86400, now,
            ),
        )
    append_audit(identity.tenant_id, identity.user_id, "document.created", "document", document_id, {"sha256": intake.sha256, "size": intake.size})
    return document_id


def document_for(identity: Identity, document_id: str):
    initialize_identity()
    with _connect() as db:
        row = db.execute(
            "SELECT * FROM documents WHERE id=? AND tenant_id=?",
            (document_id, identity.tenant_id),
        ).fetchone()
    if not row or (row["owner_user_id"] != identity.user_id and not identity.is_admin):
        raise HTTPException(status_code=404, detail="Document not found.")
    return row


def set_legal_hold(identity: Identity, document_id: str, enabled: bool) -> None:
    if not identity.is_admin:
        raise HTTPException(status_code=403, detail="Administrator role is required.")
    document_for(identity, document_id)
    with _connect() as db:
        db.execute("UPDATE documents SET legal_hold=? WHERE id=?", (int(enabled), document_id))
    append_audit(identity.tenant_id, identity.user_id, "document.hold.changed", "document", document_id, {"enabled": enabled})


def delete_document(identity: Identity, document_id: str) -> None:
    row = document_for(identity, document_id)
    if row["legal_hold"]:
        raise HTTPException(status_code=409, detail="Document is under legal hold.")
    with _connect() as db:
        jobs = db.execute(
            "SELECT id,result_path FROM jobs WHERE tenant_id=? AND json_extract(payload_json,'$.document_id')=?",
            (identity.tenant_id, document_id),
        ).fetchall()
        db.execute(
            "UPDATE documents SET status='deletion-pending' WHERE id=?",
            (document_id,),
        )
    for job in jobs:
        request_cancel(job["id"], identity.tenant_id, identity.user_id)
        secure_unlink(job["result_path"])
    secure_unlink(Path(row["source_path"]))
    with _connect() as db:
        db.execute(
            "UPDATE documents SET status='deleted',source_path='',deleted_at=? WHERE id=?",
            (time.time(), document_id),
        )
    append_audit(identity.tenant_id, identity.user_id, "document.deleted", "document", document_id, {"jobs": len(jobs)})


def expire_documents() -> int:
    initialize_identity()
    with _connect() as db:
        rows = db.execute(
            "SELECT * FROM documents WHERE status='active' AND legal_hold=0 AND retention_until < ?",
            (time.time(),),
        ).fetchall()
    for row in rows:
        delete_document(Identity(row["tenant_id"], row["owner_user_id"], "administrator", "retention-worker"), row["id"])
    return len(rows)
