"""In-memory async job registry for long-running PDF operations.

Each job has:
  - id: UUID string
  - status: "pending" | "processing" | "complete" | "failed"
  - result_path: Path to output file (when complete)
  - error: str (when failed)
  - progress: int 0-100
  - stage: str human-readable stage description
  - created_at: float timestamp

Jobs are stored in a module-level dict so they survive across requests within
the same process.  For multi-process deployments use Redis/Celery instead.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine


@dataclass
class Job:
    id: str
    status: str = "pending"          # pending | processing | complete | failed
    result_path: Path | None = None
    result_url: str | None = None
    error: str | None = None
    progress: int = 0
    stage: str = "Queued"
    created_at: float = field(default_factory=time.time)
    extra: dict[str, Any] = field(default_factory=dict)


# Module-level registry — simple dict, protected by asyncio single-thread model
_registry: dict[str, Job] = {}


def create_job() -> Job:
    """Create and register a new job, returning it."""
    job = Job(id=str(uuid.uuid4()))
    _registry[job.id] = job
    return job


def get_job(job_id: str) -> Job | None:
    return _registry.get(job_id)


def update_progress(job_id: str, progress: int, stage: str) -> None:
    """Update progress fields in-place (safe to call from a background task)."""
    job = _registry.get(job_id)
    if job:
        job.progress = progress
        job.stage = stage


async def run_job(
    job: Job,
    coro: Callable[["Job"], Coroutine[Any, Any, Path]],
) -> None:
    """Execute *coro* as a background asyncio task and update job state."""
    job.status = "processing"
    job.stage = "Starting"
    try:
        result_path = await coro(job)
        job.result_path = result_path
        job.result_url = f"/api/jobs/{job.id}/download"
        job.status = "complete"
        job.progress = 100
        job.stage = "Done"
    except Exception as exc:  # noqa: BLE001
        job.status = "failed"
        job.error = str(exc)
        job.stage = "Failed"


def purge_old_jobs(max_age_seconds: int = 3600) -> int:
    """Remove jobs older than *max_age_seconds*.  Returns count removed."""
    cutoff = time.time() - max_age_seconds
    to_delete = [jid for jid, j in _registry.items() if j.created_at < cutoff]
    for jid in to_delete:
        job = _registry.pop(jid, None)
        if job and job.result_path and job.result_path.exists():
            try:
                job.result_path.unlink()
            except OSError:
                pass
    return len(to_delete)
