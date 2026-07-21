"""Tenant-scoped durable job status, cancellation, progress, and downloads."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from makepdf.web.auth import Identity, authenticate_api_key, require_identity, sign_download, verify_download
from makepdf.web.job_registry import get_job, request_cancel

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _owned_job(job_id: str, identity: Identity):
    job = get_job(job_id, identity.tenant_id)
    if job is None or (job.user_id != identity.user_id and not identity.is_admin):
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@router.get("/{job_id}")
async def job_status(job_id: str, identity: Identity = Depends(require_identity)):
    job = _owned_job(job_id, identity)
    payload: dict = {
        "jobId": job.id,
        "status": job.status,
        "progress": job.progress,
        "stage": job.stage,
        "attempts": job.attempts,
        "expires_at": job.expires_at,
    }
    if job.status == "complete":
        token = sign_download(job.id, identity)
        payload["result_url"] = f"/api/jobs/{job.id}/download?token={token}"
    if job.status in ("failed", "cancelled"):
        payload["error"] = job.error
    return JSONResponse(content=payload)


@router.delete("/{job_id}", status_code=202)
async def cancel_job(job_id: str, identity: Identity = Depends(require_identity)):
    _owned_job(job_id, identity)
    if not request_cancel(job_id, identity.tenant_id, identity.user_id):
        raise HTTPException(status_code=409, detail="Job can no longer be cancelled.")
    return {"jobId": job_id, "status": "cancellation-requested"}


@router.get("/{job_id}/progress")
async def job_progress_sse(job_id: str, identity: Identity = Depends(require_identity)):
    _owned_job(job_id, identity)

    async def event_generator():
        while True:
            job = get_job(job_id, identity.tenant_id)
            if job is None:
                break
            yield "data: " + json.dumps(
                {"progress": job.progress, "stage": job.stage, "status": job.status}
            ) + "\n\n"
            if job.status in ("complete", "failed", "cancelled", "expired"):
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/{job_id}/download")
async def job_download(
    job_id: str,
    token: str | None = Query(None),
    api_key: str | None = Header(None, alias="X-API-Key"),
):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    identity = authenticate_api_key(api_key)
    authorized = bool(
        identity
        and identity.tenant_id == job.tenant_id
        and (identity.user_id == job.user_id or identity.is_admin)
    )
    if not authorized and token:
        signed_user = verify_download(token, job.id, job.tenant_id)
        authorized = signed_user == job.user_id
    if not authorized:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status != "complete":
        raise HTTPException(status_code=409, detail=f"Job is not complete (status={job.status}).")
    if job.result_path is None or not job.result_path.is_file():
        raise HTTPException(status_code=410, detail="Result file has expired or was deleted.")
    return FileResponse(
        path=str(job.result_path),
        media_type="application/pdf" if job.result_path.suffix.lower() == ".pdf" else "text/plain",
        filename=job.extra.get("filename", job.result_path.name),
        headers={"Cache-Control": "private, no-store"},
    )
