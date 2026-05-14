"""Routes for async job status, progress SSE, and result download."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from makepdf.web.job_registry import get_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}")
async def job_status(job_id: str):
    """Return current status of a background job.

    Response schema::

        {
          "jobId": "...",
          "status": "pending|processing|complete|failed",
          "progress": 0-100,
          "stage": "human readable",
          "result_url": "/api/jobs/{id}/download",  // only when complete
          "error": "..."                             // only when failed
        }
    """
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    payload: dict = {
        "jobId": job.id,
        "status": job.status,
        "progress": job.progress,
        "stage": job.stage,
    }
    if job.status == "complete":
        payload["result_url"] = job.result_url
    if job.status == "failed":
        payload["error"] = job.error

    return JSONResponse(content=payload)


@router.get("/{job_id}/progress")
async def job_progress_sse(job_id: str):
    """Server-Sent Events stream for live progress of a background job.

    The client receives ``data: {...}`` lines until the job reaches a terminal
    state (``complete`` or ``failed``).  Poll interval is ~0.5 s.

    Example event payload::

        {"progress": 45, "stage": "OCR page 12/50", "status": "processing"}
    """
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    async def event_generator():
        while True:
            j = get_job(job_id)
            if j is None:
                break

            data = json.dumps({
                "progress": j.progress,
                "stage": j.stage,
                "status": j.status,
            })
            yield f"data: {data}\n\n"

            if j.status in ("complete", "failed"):
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


@router.get("/{job_id}/download")
async def job_download(job_id: str):
    """Download the result file of a completed job."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if job.status != "complete":
        raise HTTPException(
            status_code=409,
            detail=f"Job is not complete yet (status={job.status}).",
        )
    if job.result_path is None or not job.result_path.exists():
        raise HTTPException(status_code=410, detail="Result file has been removed.")

    filename = job.extra.get("filename", job.result_path.name)
    return FileResponse(
        path=str(job.result_path),
        media_type="application/pdf",
        filename=filename,
    )
