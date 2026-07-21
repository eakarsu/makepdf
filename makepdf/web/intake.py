"""Bounded, streaming intake for attacker-controlled service files."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

from fastapi import HTTPException, UploadFile

from makepdf.config import (
    CLAMAV_COMMAND,
    MALWARE_SCAN_MODE,
    MAX_UPLOAD_SIZE,
    OBJECT_DIR,
    TEMP_DIR,
)
from makepdf.web.sandbox import apply_resource_limits, sanitized_environment


@dataclass(frozen=True)
class IntakeResult:
    path: Path
    sha256: str
    size: int
    pages: int | None = None


def _safe_component(value: str | None, fallback: str = "anonymous") -> str:
    candidate = "".join(char for char in (value or "") if char.isalnum() or char in "-_")
    return candidate[:80] or fallback


async def _chunks(upload: UploadFile, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        yield chunk


async def read_limited(upload: UploadFile, limit: int = MAX_UPLOAD_SIZE) -> bytes:
    """Read a non-PDF form asset without an unbounded ``UploadFile.read``."""
    content = bytearray()
    async for chunk in _chunks(upload):
        if len(content) + len(chunk) > limit:
            raise HTTPException(status_code=413, detail="Upload exceeds the configured limit.")
        content.extend(chunk)
    return bytes(content)


def _probe_limits() -> None:
    apply_resource_limits(
        cpu_seconds=15,
        memory_bytes=512 * 1024 * 1024,
        output_bytes=1024 * 1024,
        descriptors=64,
        processes=8,
    )


def _isolated_probe(kind: str, path: Path, file_size: int = 0) -> dict[str, int]:
    try:
        with tempfile.TemporaryDirectory(prefix="makepdf-probe-") as working_directory:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "makepdf.web.file_probe",
                    kind,
                    str(path.resolve()),
                    "--size",
                    str(file_size),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=20,
                check=False,
                text=True,
                cwd=working_directory,
                env=sanitized_environment(),
                start_new_session=True,
                preexec_fn=_probe_limits if os.name == "posix" else None,
            )
        if result.returncode:
            detail = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "parser rejected input"
            raise ValueError(detail[-500:])
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        if not isinstance(payload, dict):
            raise ValueError("parser returned an invalid result")
        return {str(key): int(value) for key, value in payload.items()}
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=422, detail="Unsafe or malformed file: parser timed out") from exc
    except HTTPException:
        raise
    except (IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=f"Unsafe or malformed file: {exc}") from exc


def _validate_pdf(path: Path, file_size: int) -> int:
    try:
        return _isolated_probe("pdf", path, file_size)["pages"]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Unsafe or malformed PDF: {exc}") from exc


def _validate_image(path: Path) -> None:
    try:
        _isolated_probe("image", path)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Unsafe or malformed image: {exc}") from exc


def _scan(path: Path) -> None:
    if MALWARE_SCAN_MODE == "disabled":
        return
    scanner = shutil.which(CLAMAV_COMMAND)
    if not scanner:
        if MALWARE_SCAN_MODE == "required":
            raise HTTPException(status_code=503, detail="Required malware scanner is unavailable.")
        return
    try:
        result = subprocess.run(
            [scanner, "--fdpass", "--no-summary", str(path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=60,
            check=False,
            text=True,
            env={"PATH": os.environ.get("PATH", "")},
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=503, detail="Malware scan timed out.") from exc
    if result.returncode == 1:
        raise HTTPException(status_code=422, detail="Upload was quarantined by malware scanning.")
    if result.returncode != 0:
        raise HTTPException(status_code=503, detail="Malware scanner could not verify the upload.")


async def save_upload(
    upload: UploadFile,
    suffix: str = ".pdf",
    *,
    tenant_id: str | None = None,
    durable: bool = False,
) -> IntakeResult:
    """Stream an upload to a mode-0600 quarantine file, then validate and scan it."""
    base = OBJECT_DIR / _safe_component(tenant_id) if durable else TEMP_DIR / "quarantine"
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    token = secrets.token_urlsafe(24)
    partial = base / f".{token}.partial"
    destination = base / f"{token}{suffix}"
    digest = hashlib.sha256()
    total = 0
    try:
        fd = os.open(partial, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as stream:
            async for chunk in _chunks(upload):
                total += len(chunk)
                if total > MAX_UPLOAD_SIZE:
                    raise HTTPException(status_code=413, detail="Upload exceeds the configured limit.")
                digest.update(chunk)
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        if total == 0:
            raise HTTPException(status_code=422, detail="Upload is empty.")
        pages = None
        if suffix.lower() == ".pdf":
            with partial.open("rb") as stream:
                header = stream.read(1024)
                stream.seek(max(total - 4096, 0))
                trailer = stream.read()
            if b"%PDF-" not in header or b"%%EOF" not in trailer:
                raise HTTPException(status_code=422, detail="Upload does not have a valid PDF envelope.")
            pages = _validate_pdf(partial, total)
        elif suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".webp", ".bmp"}:
            _validate_image(partial)
        _scan(partial)
        os.replace(partial, destination)
        return IntakeResult(destination, digest.hexdigest(), total, pages)
    except Exception:
        partial.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise


def secure_unlink(path: str | Path | None) -> None:
    """Unlink a temporary artifact and durably record its directory update."""
    if not path:
        return
    target = Path(path)
    try:
        target.unlink(missing_ok=True)
        if target.parent.exists():
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except OSError:
        # Lifecycle sweeps retry failures; overwriting is intentionally avoided
        # because it gives false assurance on SSD/copy-on-write storage.
        pass
