"""GET /api/ai/results — paginated AI audit log."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from makepdf.web.auth import require_api_key
from makepdf.web.ai_helpers import query_ai_results

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/results")
async def list_ai_results(
    feature: str | None = Query(None, description="Filter by feature name"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    api_key: str | None = Depends(require_api_key),
):
    """Paginated read of the AI audit log (ai_results table)."""
    body = query_ai_results(feature=feature, page=page, limit=limit)
    return JSONResponse(content=body)
