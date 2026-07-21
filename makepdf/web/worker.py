"""Isolated durable OCR worker with leases, cancellation, and resource limits."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from makepdf.config import MAX_JOB_SECONDS
from makepdf.web.governance import expire_documents
from makepdf.web.job_registry import (
    claim_next_job,
    complete_job,
    fail_job,
    get_job,
    purge_old_jobs,
    record_worker_heartbeat,
    recover_stale_jobs,
    renew_lease,
)
from makepdf.web.sandbox import apply_resource_limits, sanitized_environment

KINDS = ("ocr-extract-text", "ocr-make-searchable")
_stop = False


def _limits() -> None:
    memory = int(os.getenv("MAKEPDF_WORKER_MEMORY_MB", "1024")) * 1024 * 1024
    output = int(os.getenv("MAKEPDF_WORKER_OUTPUT_MB", "500")) * 1024 * 1024
    apply_resource_limits(
        cpu_seconds=MAX_JOB_SECONDS,
        memory_bytes=memory,
        output_bytes=output,
    )


def _environment(temp_dir: str) -> dict[str, str]:
    keep = {
        "PATH", "LANG", "LC_ALL", "TESSDATA_PREFIX", "MAKEPDF_JOB_DB",
        "MAKEPDF_DATA_DIR", "MAKEPDF_OBJECT_DIR", "MAKEPDF_TEMP_DIR",
    }
    environment = {key: value for key, value in os.environ.items() if key in keep}
    environment["TMPDIR"] = temp_dir
    return sanitized_environment(environment)


def _execute(job, worker_id: str) -> None:
    with tempfile.TemporaryDirectory(prefix="makepdf-worker-") as temp_dir:
        process = subprocess.Popen(
            [sys.executable, "-m", "makepdf.web.worker_task", "--job", job.id],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=temp_dir,
            env=_environment(temp_dir),
            start_new_session=True,
            preexec_fn=_limits if os.name == "posix" else None,
        )
        deadline = time.monotonic() + MAX_JOB_SECONDS
        while process.poll() is None:
            current = get_job(job.id)
            if current is None or current.cancel_requested:
                os.killpg(process.pid, signal.SIGTERM) if os.name == "posix" else process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL) if os.name == "posix" else process.kill()
                fail_job(job.id, worker_id, "Cancelled by user", retryable=False)
                return
            if time.monotonic() > deadline:
                os.killpg(process.pid, signal.SIGKILL) if os.name == "posix" else process.kill()
                fail_job(job.id, worker_id, "Job exceeded the configured time limit", retryable=True)
                return
            renew_lease(job.id, worker_id, 60)
            time.sleep(0.5)
        output = (process.stdout.read() if process.stdout else "").strip()
        if process.returncode:
            fail_job(job.id, worker_id, output[-1000:] or "Isolated worker failed", retryable=True)
            return
        try:
            result_path = Path(json.loads(output.splitlines()[-1])["result_path"])
        except (IndexError, KeyError, json.JSONDecodeError) as exc:
            fail_job(job.id, worker_id, f"Worker returned an invalid result: {exc}", retryable=False)
            return
        complete_job(job.id, worker_id, result_path)


def _handle_stop(_signum, _frame) -> None:
    global _stop
    _stop = True


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    worker_id = f"{os.uname().nodename if hasattr(os, 'uname') else 'worker'}:{os.getpid()}:{uuid.uuid4()}"
    recover_stale_jobs()
    last_sweep = 0.0
    while not _stop:
        record_worker_heartbeat(worker_id, KINDS)
        now = time.monotonic()
        if now - last_sweep > 60:
            purge_old_jobs()
            expire_documents()
            last_sweep = now
        job = claim_next_job(worker_id, KINDS)
        if job:
            _execute(job, worker_id)
        else:
            time.sleep(0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
