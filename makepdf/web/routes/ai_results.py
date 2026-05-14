"""GET /api/ai-results — paginated AI call audit log.

Surfaces the persisted ``ai_results`` rows (input/output/latency/success/error)
that ``persist_ai_result`` writes from every AI route. Closes the loop for
audit logging — `ai_helpers.query_ai_results()` existed but was not exposed
via HTTP, so operators had to query the SQLite DB directly.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from makepdf.web.auth import require_api_key
from makepdf.web.ai_helpers import query_ai_results, aggregate_ai_results
from makepdf.web.shared import templates

router = APIRouter(tags=["ai"])


@router.get("/api/ai-results")
def list_ai_results(
    feature: str | None = Query(default=None, description="Filter by feature name (e.g. 'summarize')"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    api_key: str | None = Depends(require_api_key),
) -> dict:
    """Paginated read of the AI audit log.

    Returns ``{results, total, page, totalPages}``. Each result row exposes
    feature, model, api_key_hash (not the key itself), input, output, success,
    error_message, latency_ms, created_at.
    """
    try:
        return query_ai_results(feature=feature, page=page, limit=limit)
    except Exception as exc:  # pragma: no cover - defensive surface
        raise HTTPException(status_code=500, detail=f"Failed to read ai_results: {exc}")


@router.get("/api/ai-results/stats")
def ai_results_stats(
    days: int = Query(default=7, ge=1, le=365, description="Window size in days"),
    feature: str | None = Query(default=None, description="Optional feature filter"),
    api_key: str | None = Depends(require_api_key),
) -> dict:
    """Aggregated AI-call stats over a recent window.

    Surfaces the existing ``aggregate_ai_results`` helper (count / success rate
    / avg+max latency per feature plus totals) — closes the loop with the
    paginated audit log so operators don't have to page through results to spot
    a regression. Reuses the same ``X-API-Key`` auth as ``/api/ai-results``.
    """
    try:
        return aggregate_ai_results(days=days, feature=feature)
    except Exception as exc:  # pragma: no cover - defensive surface
        raise HTTPException(status_code=500, detail=f"Failed to aggregate ai_results: {exc}")


@router.get("/ai-results", response_class=HTMLResponse)
async def ai_results_page(request: Request):
    """HTML viewer for the AI audit log. Calls /api/ai-results client-side."""
    return templates.TemplateResponse("ai_results.html", {"request": request})


@router.get("/ai-tools", response_class=HTMLResponse)
async def ai_tools_page(request: Request):
    """HTML page wiring the AI endpoints (classify/summarize/smart-redact/
    ai-fill-form) to a simple browser UI. Mirrors the X-API-Key + 503
    handling used by /ai-results."""
    return templates.TemplateResponse("ai_tools.html", {"request": request})
