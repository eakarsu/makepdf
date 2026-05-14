"""API key authentication dependency for FastAPI routes.

Behavior changed (security hardening):
- ``API_KEY`` env var is checked at import.
- If unset and ``MAKEPDF_ALLOW_OPEN_MODE`` is NOT set to ``1``/``true``, the
  dependency raises HTTP 503 on every protected request and a loud error is
  logged at startup. (Default is now opt-out: auth required.)
- To explicitly run unauthenticated for local dev set both:
    ``API_KEY=`` (unset) and ``MAKEPDF_ALLOW_OPEN_MODE=1``.
"""

from __future__ import annotations

import logging
import os

from fastapi import HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader

logger = logging.getLogger(__name__)

_API_KEY: str | None = os.getenv("API_KEY")
_ALLOW_OPEN_MODE: bool = os.getenv("MAKEPDF_ALLOW_OPEN_MODE", "").lower() in {"1", "true", "yes"}

if not _API_KEY and _ALLOW_OPEN_MODE:
    logger.warning(
        "MAKEPDF: running in OPEN MODE (no API key required). "
        "Set API_KEY=<secret> for production."
    )
elif not _API_KEY:
    logger.error(
        "MAKEPDF: API_KEY is not set. Protected endpoints will return 503. "
        "Set API_KEY=<secret> or, for local development only, "
        "MAKEPDF_ALLOW_OPEN_MODE=1."
    )

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str | None = Security(_api_key_header)) -> str | None:
    """Enforce X-API-Key. Returns the key (or None when in explicit open mode).

    - When ``API_KEY`` is set: the request key must match. Mismatch → 401.
    - When ``API_KEY`` is NOT set and ``MAKEPDF_ALLOW_OPEN_MODE=1``: pass.
    - Otherwise: 503 (server is mis-configured for production).
    """
    if _API_KEY:
        if api_key != _API_KEY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing X-API-Key header.",
                headers={"WWW-Authenticate": "ApiKey"},
            )
        return api_key

    if _ALLOW_OPEN_MODE:
        return api_key  # may be None in open mode

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "MakePDF server is not configured for authentication. "
            "Set API_KEY=<secret> or MAKEPDF_ALLOW_OPEN_MODE=1 for development."
        ),
    )
