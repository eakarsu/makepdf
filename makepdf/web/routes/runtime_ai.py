"""Authenticated live OpenRouter review with durable provider evidence."""

from __future__ import annotations

import os
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from makepdf.web.ai_helpers import ai_rate_limiter, persist_ai_result
from makepdf.web.auth import Identity, require_identity

router = APIRouter(prefix="/api/ai", tags=["runtime-ai"])


class ReviewRequest(BaseModel):
    prompt: str


@router.post("/pdf-governance-review", dependencies=[Depends(ai_rate_limiter)])
def review(payload: ReviewRequest, identity: Identity = Depends(require_identity)):
    prompt = payload.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    base_url = os.getenv("OPENROUTER_BASE_URL", "").rstrip("/")
    model = os.getenv("OPENROUTER_MODEL", "").strip()
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if base_url != "https://openrouter.ai/api/v1" or not model or not api_key:
        raise HTTPException(status_code=503, detail="Exact OpenRouter configuration is required")

    started = time.monotonic()
    response = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "X-Title": "MakePDF"},
        json={
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "Review PDF processing workflows for provenance, accessibility, privacy, redaction safety, and accountable human approval.",
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 650,
        },
        timeout=110.0,
    )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"OpenRouter API error ({response.status_code})")
    provider = response.json()
    content = str(provider.get("choices", [{}])[0].get("message", {}).get("content", "")).strip()
    provider_receipt = {
        "requestId": str(provider.get("id", "")),
        "provider": str(provider.get("provider", "openrouter")),
        "upstreamModel": str(provider.get("model", model)),
        "created": int(provider.get("created", 0) or 0),
    }
    if not content or not provider_receipt["requestId"]:
        raise HTTPException(status_code=502, detail="OpenRouter response or provider receipt is missing")

    output = {"content": content, "providerReceipt": provider_receipt}
    persist_ai_result(
        feature="pdf-governance-review",
        input_payload={"prompt": prompt},
        output_payload=output,
        model=model,
        api_key=identity,
        success=True,
        latency_ms=int((time.monotonic() - started) * 1000),
    )
    return {"content": content, "model": model, "providerReceipt": provider_receipt}
