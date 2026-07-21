"""Durable SQLite job queue for local and single-host production workers.

SQLite WAL plus short ``BEGIN IMMEDIATE`` claim transactions supports multiple
API and worker processes on one durable volume.  Hosted multi-node deployments
must place the database on a supported shared transactional service; network
filesystems are intentionally not claimed as safe SQLite storage.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine, Iterable

from makepdf.config import JOB_DB_PATH, JOB_MAX_ATTEMPTS, JOB_RESULT_TTL_SECONDS
from makepdf.web.intake import secure_unlink

DB_PATH = JOB_DB_PATH
TERMINAL = {"complete", "failed", "cancelled", "expired"}


@dataclass
class Job:
    id: str
    status: str = "pending"
    result_path: Path | None = None
    result_url: str | None = None
    error: str | None = None
    progress: int = 0
    stage: str = "Queued"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    tenant_id: str = "legacy"
    user_id: str = "legacy"
    kind: str = "callable"
    payload: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    attempts: int = 0
    max_attempts: int = JOB_MAX_ATTEMPTS
    cancel_requested: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    connection = sqlite3.connect(DB_PATH, timeout=5, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = FULL")
    return connection


def initialize() -> None:
    with _connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              kind TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              payload_sha256 TEXT NOT NULL,
              idempotency_key TEXT,
              status TEXT NOT NULL CHECK(status IN
                ('pending','processing','retry','complete','failed','cancelled','expired')),
              result_path TEXT,
              result_sha256 TEXT,
              filename TEXT,
              error TEXT,
              progress INTEGER NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
              stage TEXT NOT NULL DEFAULT 'Queued',
              attempts INTEGER NOT NULL DEFAULT 0,
              max_attempts INTEGER NOT NULL DEFAULT 3,
              available_at REAL NOT NULL,
              lease_owner TEXT,
              lease_until REAL,
              cancel_requested INTEGER NOT NULL DEFAULT 0,
              created_at REAL NOT NULL,
              updated_at REAL NOT NULL,
              expires_at REAL NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS jobs_idempotency_once
              ON jobs(tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
            CREATE INDEX IF NOT EXISTS jobs_claim_due
              ON jobs(status, available_at, created_at);
            CREATE INDEX IF NOT EXISTS jobs_expiry
              ON jobs(expires_at, status);

            CREATE TABLE IF NOT EXISTS worker_heartbeats (
              worker_id TEXT PRIMARY KEY,
              kinds_json TEXT NOT NULL,
              last_seen_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_events (
              sequence INTEGER PRIMARY KEY AUTOINCREMENT,
              tenant_id TEXT NOT NULL,
              user_id TEXT NOT NULL,
              action TEXT NOT NULL,
              resource_type TEXT NOT NULL,
              resource_id TEXT NOT NULL,
              details_json TEXT NOT NULL,
              previous_hash TEXT NOT NULL,
              event_hash TEXT NOT NULL UNIQUE,
              created_at REAL NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS audit_events_no_update
              BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
              BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
            """
        )


def _job(row: sqlite3.Row | None) -> Job | None:
    if row is None:
        return None
    payload = json.loads(row["payload_json"])
    filename = row["filename"]
    return Job(
        id=row["id"],
        status=row["status"],
        result_path=Path(row["result_path"]) if row["result_path"] else None,
        result_url=f"/api/jobs/{row['id']}/download" if row["status"] == "complete" else None,
        error=row["error"],
        progress=row["progress"],
        stage=row["stage"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=row["expires_at"],
        tenant_id=row["tenant_id"],
        user_id=row["user_id"],
        kind=row["kind"],
        payload=payload,
        idempotency_key=row["idempotency_key"],
        attempts=row["attempts"],
        max_attempts=row["max_attempts"],
        cancel_requested=bool(row["cancel_requested"]),
        extra={"filename": filename} if filename else {},
    )


def append_audit(
    tenant_id: str,
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    details: dict[str, Any] | None = None,
) -> str:
    initialize()
    now = time.time()
    body = json.dumps(details or {}, sort_keys=True, separators=(",", ":"))
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute(
            "SELECT event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = previous[0] if previous else "0" * 64
        material = "|".join(
            (previous_hash, tenant_id, user_id, action, resource_type, resource_id, body, str(now))
        )
        event_hash = hashlib.sha256(material.encode()).hexdigest()
        db.execute(
            "INSERT INTO audit_events(tenant_id,user_id,action,resource_type,resource_id,"
            "details_json,previous_hash,event_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (tenant_id, user_id, action, resource_type, resource_id, body, previous_hash, event_hash, now),
        )
        db.commit()
    return event_hash


def create_job(
    *,
    tenant_id: str = "legacy",
    user_id: str = "legacy",
    kind: str = "callable",
    payload: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    filename: str | None = None,
    max_attempts: int = JOB_MAX_ATTEMPTS,
) -> Job:
    """Create a job or return the exact prior request for an idempotency key."""
    initialize()
    payload = payload or {}
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    # Storage identifiers change on a retried HTTP upload; the content digest
    # and operation parameters define the idempotent request.
    semantic_payload = {
        key: value for key, value in payload.items()
        if key not in {"source_path", "document_id", "result_dir"}
    }
    semantic_json = json.dumps(semantic_payload, sort_keys=True, separators=(",", ":"))
    payload_sha = hashlib.sha256(f"{kind}|{semantic_json}".encode()).hexdigest()
    now = time.time()
    job_id = str(uuid.uuid4())
    with _connect() as db:
        try:
            db.execute(
                "INSERT INTO jobs(id,tenant_id,user_id,kind,payload_json,payload_sha256,"
                "idempotency_key,status,filename,available_at,created_at,updated_at,expires_at,max_attempts) "
                "VALUES(?,?,?,?,?,?,?,'pending',?,?,?,?,?,?)",
                (
                    job_id, tenant_id, user_id, kind, payload_json, payload_sha,
                    idempotency_key, filename, now, now, now,
                    now + JOB_RESULT_TTL_SECONDS, max_attempts,
                ),
            )
        except sqlite3.IntegrityError:
            if not idempotency_key:
                raise
            row = db.execute(
                "SELECT * FROM jobs WHERE tenant_id=? AND idempotency_key=?",
                (tenant_id, idempotency_key),
            ).fetchone()
            if row is None or row["payload_sha256"] != payload_sha:
                raise ValueError("Idempotency key was already used for a different request.")
            return _job(row)  # type: ignore[return-value]
    append_audit(tenant_id, user_id, "job.created", "job", job_id, {"kind": kind})
    return get_job(job_id)  # type: ignore[return-value]


def get_job(job_id: str, tenant_id: str | None = None) -> Job | None:
    initialize()
    query = "SELECT * FROM jobs WHERE id=?"
    values: tuple[Any, ...] = (job_id,)
    if tenant_id is not None:
        query += " AND tenant_id=?"
        values += (tenant_id,)
    with _connect() as db:
        return _job(db.execute(query, values).fetchone())


def update_progress(job_id: str, progress: int, stage: str, lease_owner: str | None = None) -> None:
    initialize()
    progress = min(max(int(progress), 0), 100)
    query = "UPDATE jobs SET progress=?,stage=?,updated_at=? WHERE id=?"
    values: list[Any] = [progress, stage[:200], time.time(), job_id]
    if lease_owner:
        query += " AND lease_owner=?"
        values.append(lease_owner)
    with _connect() as db:
        db.execute(query, values)


def recover_stale_jobs(now: float | None = None) -> int:
    initialize()
    now = now or time.time()
    with _connect() as db:
        result = db.execute(
            "UPDATE jobs SET status='retry',stage='Recovered after worker restart',"
            "lease_owner=NULL,lease_until=NULL,available_at=?,updated_at=? "
            "WHERE status='processing' AND lease_until < ? AND cancel_requested=0",
            (now, now, now),
        )
        return result.rowcount


def record_worker_heartbeat(worker_id: str, kinds: Iterable[str]) -> None:
    initialize()
    with _connect() as db:
        db.execute(
            "INSERT INTO worker_heartbeats(worker_id,kinds_json,last_seen_at) VALUES(?,?,?) "
            "ON CONFLICT(worker_id) DO UPDATE SET kinds_json=excluded.kinds_json,last_seen_at=excluded.last_seen_at",
            (worker_id, json.dumps(sorted(kinds)), time.time()),
        )


def active_worker_count(max_age_seconds: int = 30) -> int:
    initialize()
    with _connect() as db:
        return int(db.execute(
            "SELECT count(*) FROM worker_heartbeats WHERE last_seen_at>=?",
            (time.time() - max_age_seconds,),
        ).fetchone()[0])


def claim_next_job(worker_id: str, kinds: Iterable[str], lease_seconds: int = 60) -> Job | None:
    initialize()
    allowed = tuple(kinds)
    if not allowed:
        return None
    now = time.time()
    placeholders = ",".join("?" for _ in allowed)
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "UPDATE jobs SET status='retry',lease_owner=NULL,lease_until=NULL,"
            "stage='Recovered after worker restart',available_at=?,updated_at=? "
            "WHERE status='processing' AND lease_until < ? AND cancel_requested=0",
            (now, now, now),
        )
        row = db.execute(
            f"SELECT id FROM jobs WHERE status IN ('pending','retry') "
            f"AND available_at<=? AND cancel_requested=0 AND kind IN ({placeholders}) "
            "ORDER BY created_at LIMIT 1",
            (now, *allowed),
        ).fetchone()
        if not row:
            db.commit()
            return None
        db.execute(
            "UPDATE jobs SET status='processing',attempts=attempts+1,progress=1,"
            "stage='Claimed by isolated worker',lease_owner=?,lease_until=?,updated_at=? WHERE id=?",
            (worker_id, now + lease_seconds, now, row["id"]),
        )
        db.commit()
    return get_job(row["id"])


def renew_lease(job_id: str, worker_id: str, lease_seconds: int = 60) -> bool:
    with _connect() as db:
        result = db.execute(
            "UPDATE jobs SET lease_until=?,updated_at=? WHERE id=? AND status='processing' AND lease_owner=?",
            (time.time() + lease_seconds, time.time(), job_id, worker_id),
        )
        return result.rowcount == 1


def request_cancel(job_id: str, tenant_id: str, user_id: str) -> bool:
    initialize()
    now = time.time()
    with _connect() as db:
        result = db.execute(
            "UPDATE jobs SET cancel_requested=1,status=CASE WHEN status IN ('pending','retry') "
            "THEN 'cancelled' ELSE status END,stage='Cancellation requested',updated_at=? "
            "WHERE id=? AND tenant_id=? AND status NOT IN ('complete','failed','cancelled','expired')",
            (now, job_id, tenant_id),
        )
    if result.rowcount:
        append_audit(tenant_id, user_id, "job.cancelled", "job", job_id)
    return result.rowcount == 1


def complete_job(job_id: str, worker_id: str, result_path: Path, filename: str | None = None) -> None:
    data_sha = hashlib.sha256(result_path.read_bytes()).hexdigest()
    now = time.time()
    with _connect() as db:
        row = db.execute("SELECT tenant_id,user_id,cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row or row["cancel_requested"]:
            secure_unlink(result_path)
            if row:
                db.execute("UPDATE jobs SET status='cancelled',stage='Cancelled',updated_at=? WHERE id=?", (now, job_id))
            return
        result = db.execute(
            "UPDATE jobs SET status='complete',result_path=?,result_sha256=?,filename=COALESCE(?,filename),"
            "progress=100,stage='Done',lease_owner=NULL,lease_until=NULL,updated_at=? "
            "WHERE id=? AND status='processing' AND lease_owner=?",
            (str(result_path), data_sha, filename, now, job_id, worker_id),
        )
    if result.rowcount:
        append_audit(row["tenant_id"], row["user_id"], "job.completed", "job", job_id, {"sha256": data_sha})


def fail_job(job_id: str, worker_id: str, error: str, retryable: bool = True) -> None:
    now = time.time()
    with _connect() as db:
        row = db.execute("SELECT tenant_id,user_id,attempts,max_attempts,cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return
        cancelled = bool(row["cancel_requested"])
        retry = retryable and not cancelled and row["attempts"] < row["max_attempts"]
        status = "cancelled" if cancelled else ("retry" if retry else "failed")
        delay = min(300, 2 ** max(row["attempts"], 1)) if retry else 0
        db.execute(
            "UPDATE jobs SET status=?,error=?,stage=?,available_at=?,lease_owner=NULL,lease_until=NULL,updated_at=? "
            "WHERE id=? AND lease_owner=?",
            (status, error[:1000], "Retry scheduled" if retry else status.title(), now + delay, now, job_id, worker_id),
        )
    append_audit(row["tenant_id"], row["user_id"], f"job.{status}", "job", job_id, {"error": error[:300]})


async def run_job(job: Job, coro: Callable[[Job], Coroutine[Any, Any, Path]]) -> None:
    """Compatibility executor for tests/development; production uses worker.py."""
    worker_id = f"in-process:{uuid.uuid4()}"
    with _connect() as db:
        db.execute(
            "UPDATE jobs SET status='processing',attempts=attempts+1,lease_owner=?,lease_until=?,stage='Starting' WHERE id=?",
            (worker_id, time.time() + 3600, job.id),
        )
    try:
        result_path = await coro(job)
        complete_job(job.id, worker_id, result_path, job.extra.get("filename"))
    except asyncio.CancelledError:
        request_cancel(job.id, job.tenant_id, job.user_id)
        raise
    except Exception as exc:  # noqa: BLE001
        fail_job(job.id, worker_id, str(exc), retryable=False)


def purge_old_jobs(max_age_seconds: int | None = None) -> int:
    """Expire results and their source objects after TTL; audit rows remain."""
    initialize()
    now = time.time()
    cutoff = now - max_age_seconds if max_age_seconds is not None else now
    with _connect() as db:
        rows = db.execute(
            "SELECT id,tenant_id,user_id,result_path,payload_json FROM jobs "
            "WHERE status IN ('complete','failed','cancelled') AND expires_at < ?",
            (cutoff,),
        ).fetchall()
        for row in rows:
            secure_unlink(row["result_path"])
            payload = json.loads(row["payload_json"])
            secure_unlink(payload.get("source_path"))
            db.execute(
                "UPDATE jobs SET status='expired',result_path=NULL,payload_json='{}',"
                "stage='Expired and deleted',updated_at=? WHERE id=?",
                (now, row["id"]),
            )
            append_audit(row["tenant_id"], row["user_id"], "job.expired", "job", row["id"])
    return len(rows)


def list_audit(tenant_id: str, limit: int = 100) -> list[dict[str, Any]]:
    initialize()
    with _connect() as db:
        rows = db.execute(
            "SELECT * FROM audit_events WHERE tenant_id=? ORDER BY sequence DESC LIMIT ?",
            (tenant_id, min(max(limit, 1), 1000)),
        ).fetchall()
    return [dict(row) | {"details": json.loads(row["details_json"])} for row in rows]
