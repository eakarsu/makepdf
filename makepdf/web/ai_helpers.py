"""Shared AI helpers for MakePDF web routes.

Provides:
- ``DEFAULT_MODEL``      — env-overridable model id (defaults to
                            anthropic/claude-3-5-sonnet-20241022).
- ``call_openrouter``    — single OpenRouter chat completion entry point.
- ``parse_ai_json``      — 3-strategy JSON parser (matches the project pattern).
- ``ai_rate_limiter``    — FastAPI dependency, 20 calls / hour per API key
                            (or per IP when running open-mode).
- ``persist_ai_result``  — append a structured JSONB row to a SQLite log
                            with the full input, output, latency, success.
- ``query_ai_results``   — paginated read.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Optional

import httpx
from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model & request defaults
# ---------------------------------------------------------------------------
DEFAULT_MODEL = os.environ.get(
    "OPENROUTER_MODEL", "anthropic/claude-3-5-sonnet-20241022"
)
DEFAULT_VISION_MODEL = os.environ.get(
    "OPENROUTER_VISION_MODEL", DEFAULT_MODEL
)
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def call_openrouter(
    messages: list[dict],
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.2,
    timeout: float = 60.0,
    max_tokens: Optional[int] = None,
) -> str:
    """Synchronous OpenRouter chat completion. Returns choices[0] content."""
    resolved_key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not resolved_key:
        raise HTTPException(
            status_code=503,
            detail="OPENROUTER_API_KEY environment variable is not configured.",
        )

    headers = {
        "Authorization": f"Bearer {resolved_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.environ.get("MAKEPDF_PUBLIC_URL", "https://github.com/makepdf/makepdf"),
        "X-Title": "MakePDF",
    }
    payload = {
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    try:
        response = httpx.post(OPENROUTER_URL, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"OpenRouter error {e.response.status_code}: {e.response.text}",
        ) from e
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Network error: {e}") from e

    data = response.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise HTTPException(status_code=502, detail=f"Unexpected OpenRouter response: {data}") from e


# ---------------------------------------------------------------------------
# 3-strategy JSON parser
# ---------------------------------------------------------------------------
def parse_ai_json(raw: str) -> Any:
    """Three-strategy JSON parser:

    1) parse the whole stripped string
    2) strip ```json fences and parse
    3) regex-extract first {...} or [...] block and parse

    Raises ValueError when all strategies fail.
    """
    if raw is None or raw == "":
        raise ValueError("parse_ai_json: empty input")
    s = str(raw).strip()

    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    fenced = re.sub(r"```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    fenced = fenced.replace("```", "").strip()
    try:
        return json.loads(fenced)
    except json.JSONDecodeError:
        pass

    obj = re.search(r"\{[\s\S]*\}", fenced)
    if obj:
        try:
            return json.loads(obj.group(0))
        except json.JSONDecodeError:
            pass
    arr = re.search(r"\[[\s\S]*\]", fenced)
    if arr:
        try:
            return json.loads(arr.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"parse_ai_json: failed all 3 strategies. raw[:300]={raw[:300]!r}")


# ---------------------------------------------------------------------------
# Rate limiter: 20 / hour, keyed by API key (or IP when in open mode)
# ---------------------------------------------------------------------------
_rate_lock = threading.Lock()
_rate_log: dict[str, list[float]] = {}
_RATE_WINDOW = 3600.0
_RATE_MAX = 20


def _rate_check(key: str) -> None:
    now = time.time()
    with _rate_lock:
        bucket = _rate_log.setdefault(key, [])
        while bucket and now - bucket[0] > _RATE_WINDOW:
            bucket.pop(0)
        if len(bucket) >= _RATE_MAX:
            wait = int(_RATE_WINDOW - (now - bucket[0]))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"AI rate limit exceeded: {_RATE_MAX} per hour. Retry in {wait}s.",
            )
        bucket.append(now)


async def ai_rate_limiter(request: Request) -> None:
    """FastAPI dependency — limit AI endpoints to 20 calls / hour."""
    api_key = request.headers.get("X-API-Key") or ""
    key = api_key or f"ip:{request.client.host if request.client else 'unknown'}"
    _rate_check(key)


# ---------------------------------------------------------------------------
# AI result persistence (JSONB-style log via SQLite)
# ---------------------------------------------------------------------------
DB_PATH = Path(
    os.environ.get(
        "MAKEPDF_AI_LOG_DB",
        str(Path(os.environ.get("MAKEPDF_DATA_DIR", str(Path.home() / ".makepdf"))) / "ai_results.db"),
    )
)


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.execute(
        """CREATE TABLE IF NOT EXISTS ai_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feature TEXT NOT NULL,
            model TEXT,
            api_key_hash TEXT,
            input TEXT NOT NULL,
            output TEXT,
            success INTEGER NOT NULL DEFAULT 1,
            error_message TEXT,
            latency_ms INTEGER,
            created_at REAL NOT NULL
        )"""
    )
    c.execute("CREATE INDEX IF NOT EXISTS ai_results_feature_created ON ai_results(feature, created_at)")
    return c


def persist_ai_result(
    *,
    feature: str,
    input_payload: Any,
    output_payload: Any = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    latency_ms: Optional[int] = None,
) -> None:
    """Append a row to the ai_results log."""
    try:
        api_key_hash = None
        if api_key:
            import hashlib
            api_key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]

        with _conn() as c:
            c.execute(
                """INSERT INTO ai_results
                   (feature, model, api_key_hash, input, output, success, error_message, latency_ms, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    feature,
                    model or DEFAULT_MODEL,
                    api_key_hash,
                    json.dumps(input_payload, default=str),
                    json.dumps(output_payload, default=str) if output_payload is not None else None,
                    1 if success else 0,
                    error_message,
                    latency_ms,
                    time.time(),
                ),
            )
    except Exception as e:
        logger.warning("persist_ai_result failed: %s", e)


def query_ai_results(
    *,
    feature: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
) -> dict:
    """Paginated read of ai_results. Returns ``{results, total, page, totalPages}``."""
    page = max(1, int(page))
    limit = max(1, min(int(limit), 100))
    offset = (page - 1) * limit

    where = ""
    params: list[Any] = []
    if feature:
        where = "WHERE feature = ?"
        params.append(feature)

    with _conn() as c:
        total = c.execute(f"SELECT COUNT(*) FROM ai_results {where}", params).fetchone()[0]
        rows = c.execute(
            f"""SELECT id, feature, model, api_key_hash, input, output, success,
                       error_message, latency_ms, created_at
                FROM ai_results
                {where}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()

    results = [
        {
            "id": r[0],
            "feature": r[1],
            "model": r[2],
            "apiKeyHash": r[3],
            "input": json.loads(r[4]) if r[4] else None,
            "output": json.loads(r[5]) if r[5] else None,
            "success": bool(r[6]),
            "errorMessage": r[7],
            "latencyMs": r[8],
            "createdAt": r[9],
        }
        for r in rows
    ]

    return {
        "results": results,
        "total": total,
        "page": page,
        "totalPages": (total + limit - 1) // limit if total else 0,
    }


def aggregate_ai_results(
    *,
    days: int = 7,
    feature: Optional[str] = None,
) -> dict:
    """Aggregate ai_results by feature over a recent window.

    Returns ``{since, until, perFeature:[{feature,count,successCount,errorCount,
    successRate,avgLatencyMs,maxLatencyMs}], totals:{count,successCount,errorCount,
    successRate}}``.

    Mechanical follow-up to ``query_ai_results``: the existing log already
    captures latency, success and error_message — this just summarizes it so
    operators don't have to page through results to spot a regression.
    """
    days = max(1, min(int(days), 365))
    until = time.time()
    since = until - days * 86400.0

    where = "WHERE created_at >= ?"
    params: list[Any] = [since]
    if feature:
        where += " AND feature = ?"
        params.append(feature)

    with _conn() as c:
        rows = c.execute(
            f"""SELECT feature,
                       COUNT(*) AS total,
                       SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS ok,
                       SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS err,
                       AVG(CASE WHEN latency_ms IS NOT NULL THEN latency_ms END) AS avg_lat,
                       MAX(CASE WHEN latency_ms IS NOT NULL THEN latency_ms END) AS max_lat
                FROM ai_results
                {where}
                GROUP BY feature
                ORDER BY total DESC""",
            params,
        ).fetchall()

    per_feature = []
    total_count = 0
    total_ok = 0
    total_err = 0
    for r in rows:
        feat, total, ok, err, avg_lat, max_lat = r
        ok = int(ok or 0)
        err = int(err or 0)
        total = int(total or 0)
        total_count += total
        total_ok += ok
        total_err += err
        per_feature.append({
            "feature": feat,
            "count": total,
            "successCount": ok,
            "errorCount": err,
            "successRate": round(ok / total, 4) if total else 0.0,
            "avgLatencyMs": int(avg_lat) if avg_lat is not None else None,
            "maxLatencyMs": int(max_lat) if max_lat is not None else None,
        })

    return {
        "since": since,
        "until": until,
        "days": days,
        "perFeature": per_feature,
        "totals": {
            "count": total_count,
            "successCount": total_ok,
            "errorCount": total_err,
            "successRate": round(total_ok / total_count, 4) if total_count else 0.0,
        },
    }
