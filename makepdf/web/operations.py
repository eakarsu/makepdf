"""Production configuration validation and low-cardinality service metrics."""

from __future__ import annotations

import os
import shutil
import threading
import time
from collections import Counter

from makepdf.config import CLAMAV_COMMAND, DATA_DIR, MALWARE_SCAN_MODE, SERVICE_ENV
from makepdf.web.auth import _download_keys, initialize_identity
from makepdf.web.job_registry import active_worker_count


def configuration_errors(require_worker: bool = False) -> list[str]:
    errors: list[str] = []
    if SERVICE_ENV != "production":
        return errors
    if not os.getenv("API_KEY"):
        errors.append("API_KEY bootstrap identity is not configured")
    if len(os.getenv("API_KEY", "")) < 32:
        errors.append("API_KEY must contain at least 32 characters")
    if len(os.getenv("MAKEPDF_API_KEY_PEPPER", "")) < 32:
        errors.append("MAKEPDF_API_KEY_PEPPER must contain at least 32 characters")
    try:
        _download_keys()
    except RuntimeError as exc:
        errors.append(str(exc))
    if MALWARE_SCAN_MODE != "required" or not shutil.which(CLAMAV_COMMAND):
        errors.append("a required ClamAV-compatible scanner must be available")
    if str(DATA_DIR).startswith(("/tmp", "/private/tmp")):
        errors.append("MAKEPDF_DATA_DIR must be a durable encrypted volume")
    if os.getenv("MAKEPDF_ALLOW_EXTERNAL_AI", "").lower() in {"1", "true", "yes"}:
        if not os.getenv("OPENROUTER_API_KEY"):
            errors.append("external AI is enabled without OPENROUTER_API_KEY")
        if not os.getenv("MAKEPDF_AI_DPA_REFERENCE"):
            errors.append("external AI requires MAKEPDF_AI_DPA_REFERENCE")
    if os.getenv("MAKEPDF_ALLOW_CLOUD", "").lower() in {"1", "true", "yes"}:
        if not os.getenv("MAKEPDF_CLOUD_IMPORT_DOMAINS"):
            errors.append("cloud imports require an explicit hostname allowlist")
    try:
        initialize_identity()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"service database is unavailable: {exc}")
    if require_worker and not errors and active_worker_count() < 1:
        errors.append("no durable-job worker heartbeat is active")
    return errors


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: Counter[tuple[str, str]] = Counter()
        self._latency: Counter[str] = Counter()
        self.started_at = time.time()

    def observe(self, method: str, status_code: int, elapsed: float) -> None:
        family = f"{status_code // 100}xx"
        with self._lock:
            self._requests[(method, family)] += 1
            self._latency[family] += int(elapsed * 1000)

    def render(self) -> str:
        lines = [
            "# HELP makepdf_uptime_seconds Process uptime.",
            "# TYPE makepdf_uptime_seconds gauge",
            f"makepdf_uptime_seconds {int(time.time() - self.started_at)}",
            "# HELP makepdf_http_requests_total HTTP requests by method and status family.",
            "# TYPE makepdf_http_requests_total counter",
        ]
        with self._lock:
            for (method, family), count in sorted(self._requests.items()):
                lines.append(f'makepdf_http_requests_total{{method="{method}",status="{family}"}} {count}')
            lines.extend((
                "# HELP makepdf_http_latency_milliseconds_total Accumulated request latency.",
                "# TYPE makepdf_http_latency_milliseconds_total counter",
            ))
            for family, elapsed in sorted(self._latency.items()):
                lines.append(f'makepdf_http_latency_milliseconds_total{{status="{family}"}} {elapsed}')
        lines.append(f"makepdf_active_workers {active_worker_count()}")
        return "\n".join(lines) + "\n"


metrics = Metrics()
