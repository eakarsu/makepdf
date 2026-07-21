"""Single-job child entrypoint; launched only by the resource-limited worker."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import secrets
from pathlib import Path

from makepdf.web.job_registry import get_job
from makepdf.web.routes.ocr_async import _run_ocr_extract_text, _run_ocr_make_searchable


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    args = parser.parse_args()
    job = get_job(args.job)
    if not job or job.status != "processing":
        raise SystemExit("Job is not claimable")
    source = Path(job.payload["source_path"])
    actual = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual != job.payload["source_sha256"]:
        raise SystemExit("Source object checksum mismatch")
    language = str(job.payload["language"])
    if job.kind == "ocr-extract-text":
        result = asyncio.run(_run_ocr_extract_text(source, language, job))
        suffix = ".txt"
    elif job.kind == "ocr-make-searchable":
        result = asyncio.run(_run_ocr_make_searchable(source, language, job))
        suffix = ".pdf"
    else:
        raise SystemExit(f"Unsupported job kind: {job.kind}")

    destination_dir = Path(job.payload["result_dir"])
    destination_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = destination_dir / f"result-{job.id}-{secrets.token_hex(6)}{suffix}"
    os.replace(result, destination)
    destination.chmod(0o600)
    print(json.dumps({"result_path": str(destination)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
