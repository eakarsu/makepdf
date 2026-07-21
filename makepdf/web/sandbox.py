"""Shared resource limits and environment scrubbing for untrusted subprocesses."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping

try:  # POSIX containment; production containers add cgroup limits.
    import resource
except ImportError:  # pragma: no cover - Windows
    resource = None  # type: ignore[assignment]


def apply_resource_limits(
    *,
    cpu_seconds: int,
    memory_bytes: int,
    output_bytes: int,
    descriptors: int = 128,
    processes: int = 32,
) -> None:
    """Apply best-effort child limits without weakening a stricter parent limit."""
    if resource is not None:
        def constrain(kind: int, requested: tuple[int, int]) -> None:
            try:
                _soft, hard = resource.getrlimit(kind)
                soft_target = min(requested[0], hard) if hard != resource.RLIM_INFINITY else requested[0]
                hard_target = min(requested[1], hard) if hard != resource.RLIM_INFINITY else requested[1]
                resource.setrlimit(kind, (soft_target, hard_target))
            except (OSError, ValueError):
                pass

        constrain(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 2))
        constrain(resource.RLIMIT_FSIZE, (output_bytes, output_bytes))
        constrain(resource.RLIMIT_NOFILE, (descriptors, descriptors))
        # macOS applies these limits in ways that can prevent framework and
        # Poppler startup. Linux production also has container cgroup limits.
        if sys.platform != "darwin":
            constrain(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
            if hasattr(resource, "RLIMIT_NPROC"):
                constrain(resource.RLIMIT_NPROC, (processes, processes))
    os.umask(0o077)


def sanitized_environment(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return a minimal child environment with networking explicitly bypassed."""
    keep = {"PATH", "LANG", "LC_ALL", "TESSDATA_PREFIX"}
    environment = {key: value for key, value in os.environ.items() if key in keep}
    environment.update({"NO_PROXY": "*", "no_proxy": "*"})
    if extra:
        environment.update(extra)
    return environment
