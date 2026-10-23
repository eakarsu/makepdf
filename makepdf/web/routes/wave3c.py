"""Wave 3C: authenticated PDF job tasks, job search/filter + export, AI helpers.

Tasks are tenant/user scoped (in-process store, matching workspaces.py).
Jobs are the app's main records, read from the durable job registry DB.
AI: provider only when a key is configured, else deterministic fallback
labelled aiGenerated=False — never fake success.
"""
from __future__ import annotations

import csv
import io
import os
import time
import uuid
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from makepdf.web.auth import Identity, require_identity
from makepdf.web.job_registry import _connect, initialize

page_router = APIRouter(tags=["wave3c"])


@page_router.get("/wave3c", response_class=HTMLResponse)
async def wave3c_page(request: Request):
    from makepdf.web.shared import templates

    return templates.TemplateResponse("wave3c.html", {"request": request})


router = APIRouter(prefix="/api/wave3c", tags=["wave3c"])
STATUSES = {"open", "in_progress", "done"}
_TASKS: dict[str, dict[str, Any]] = {}


class TaskIn(BaseModel):
    title: str
    notes: Optional[str] = ""
    status: Optional[str] = "open"
    job_id: Optional[str] = None


class TaskPatch(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None


def _owner(identity: Identity) -> str:
    return f"{identity.tenant_id}:{identity.user_id}"


@router.get("/tasks")
def list_tasks(search: str = "", status: str = "", identity: Identity = Depends(require_identity)):
    out = [t for t in _TASKS.values() if t["owner"] == _owner(identity)]
    if status:
        out = [t for t in out if t["status"] == status]
    if search:
        q = search.lower()
        out = [t for t in out if q in t["title"].lower() or q in (t["notes"] or "").lower()]
    out.sort(key=lambda t: t["created_at"], reverse=True)
    return {"data": [{k: v for k, v in t.items() if k != "owner"} for t in out], "total": len(out)}


@router.post("/tasks", status_code=201)
def create_task(payload: TaskIn, identity: Identity = Depends(require_identity)):
    title = payload.title.strip()
    if not title or len(title) > 200:
        raise HTTPException(400, "title must be 1-200 characters")
    if payload.status not in STATUSES:
        raise HTTPException(400, "status is invalid")
    task = {"id": str(uuid.uuid4()), "owner": _owner(identity), "title": title,
            "notes": (payload.notes or "")[:2000], "status": payload.status,
            "job_id": payload.job_id, "created_at": time.time(), "updated_at": time.time()}
    _TASKS[task["id"]] = task
    return {"task": {k: v for k, v in task.items() if k != "owner"}}


@router.patch("/tasks/{task_id}")
def update_task(task_id: str, payload: TaskPatch, identity: Identity = Depends(require_identity)):
    task = _TASKS.get(task_id)
    if not task or task["owner"] != _owner(identity):
        raise HTTPException(404, "Task not found")
    if payload.status is not None and payload.status not in STATUSES:
        raise HTTPException(400, "status is invalid")
    if payload.title is not None:
        if not payload.title.strip():
            raise HTTPException(400, "title must be 1-200 characters")
        task["title"] = payload.title.strip()
    if payload.notes is not None:
        task["notes"] = payload.notes[:2000]
    if payload.status is not None:
        task["status"] = payload.status
    task["updated_at"] = time.time()
    return {"task": {k: v for k, v in task.items() if k != "owner"}}


def list_jobs(identity: Identity, search: str = "", status: str = "") -> list[dict[str, Any]]:
    initialize()
    with _connect() as db:
        rows = db.execute(
            "SELECT id,kind,status,progress,stage,attempts,created_at,updated_at,user_id FROM jobs "
            "WHERE tenant_id=? ORDER BY created_at DESC LIMIT 1000", (identity.tenant_id,)).fetchall()
    out = [dict(r) for r in rows if identity.is_admin or r["user_id"] == identity.user_id]
    for j in out:
        j.pop("user_id", None)
    if status:
        out = [j for j in out if j["status"] == status]
    if search:
        q = search.lower()
        out = [j for j in out if q in j["id"].lower() or q in j["kind"].lower() or q in (j["stage"] or "").lower()]
    return out


@router.get("/jobs")
def jobs(search: str = "", status: str = "", identity: Identity = Depends(require_identity)):
    out = list_jobs(identity, search, status)
    return {"data": out, "total": len(out)}


@router.get("/jobs/export")
def jobs_export(format: str = "json", search: str = "", status: str = "", identity: Identity = Depends(require_identity)):
    out = list_jobs(identity, search, status)
    if format.lower() == "csv":
        buf = io.StringIO()
        cols = ["id", "kind", "status", "progress", "stage", "attempts", "created_at", "updated_at"]
        w = csv.DictWriter(buf, fieldnames=cols)
        w.writeheader()
        for row in out:
            w.writerow({c: row.get(c) for c in cols})
        return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                                 headers={"Content-Disposition": 'attachment; filename="jobs.csv"'})
    return {"data": out, "total": len(out)}


def _fallback(feature: str, sections: dict[str, Any]) -> dict[str, Any]:
    return {"provider": "deterministic-fallback", "aiGenerated": False,
            "label": "Deterministic fallback — no AI provider configured. Computed locally from your records; not AI-generated.",
            "feature": feature, "sections": sections}


def job_summary(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    for j in jobs:
        by_status[j.get("status") or "unknown"] = by_status.get(j.get("status") or "unknown", 0) + 1
    failed = [j for j in jobs if j.get("status") == "failed"]
    return _fallback("job-summary", {
        "summary": f"{len(jobs)} PDF job(s) reviewed; {len(failed)} failed.",
        "metrics": {"totalJobs": len(jobs), "byStatus": by_status, "failedJobs": len(failed),
                    "hasFailedJobs": bool(failed)},
        "findings": [f"{j.get('id')}: kind={j.get('kind')}, status={j.get('status')}" for j in jobs[:10]],
        "recommendations": ["Retry failed jobs after checking the stage message."] if failed else ["No failed jobs need attention."]})


def document_checklist(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    incomplete = [j for j in jobs if j.get("status") not in ("complete",)]
    return _fallback("document-checklist", {
        "summary": f"{len(jobs)} job(s) checked; {len(incomplete)} not complete.",
        "metrics": {"totalJobs": len(jobs), "incompleteJobs": len(incomplete),
                    "allComplete": bool(jobs) and not incomplete},
        "findings": [f"{j.get('id')}: stage={j.get('stage') or 'not provided'}, progress={j.get('progress', 0)}" for j in incomplete[:10]],
        "recommendations": ["Wait for processing jobs to finish before downloading results."] if incomplete else ["All recorded jobs are complete."]})


def _maybe_provider(fallback: dict[str, Any]) -> dict[str, Any]:
    key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENROUTER_MODEL")
    if not key or not model:
        return fallback
    try:
        import json as _json
        r = httpx.post("https://openrouter.ai/api/v1/chat/completions",
                       headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                       json={"model": model, "messages": [
                           {"role": "system", "content": "Return ONLY JSON {summary:string, findings:string[], recommendations:string[], metrics:object}. Preserve false/0 values."},
                           {"role": "user", "content": _json.dumps(fallback["sections"])[:8000]}]}, timeout=60)
        if r.status_code >= 400:
            return fallback
        content = r.json()["choices"][0]["message"]["content"]
        parsed = _json.loads(content.strip().removeprefix("```json").removesuffix("```"))
        return {"provider": "openrouter", "aiGenerated": True, "model": model,
                "feature": fallback["feature"], "sections": parsed}
    except Exception:
        return fallback


def failed_job_diagnosis(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [j for j in jobs if j.get("status") == "failed"]
    return _fallback("failed-job-diagnosis", {
        "summary": f"{len(failed)} failed job(s) out of {len(jobs)} reviewed.",
        "metrics": {"totalJobs": len(jobs), "failedJobs": len(failed), "hasFailedJobs": bool(failed),
                    "retriedJobs": sum(1 for j in failed if (j.get("attempts") or 0) > 1)},
        "findings": [f"{j.get('id')}: kind={j.get('kind')}, stage={j.get('stage') or 'not provided'}, attempts={j.get('attempts', 0)}" for j in failed[:10]],
        "recommendations": ["Open the failed stage message, fix the input, then retry once."] if failed else ["No failed jobs to diagnose."]})


@router.post("/ai/job-summary")
def ai_job_summary(identity: Identity = Depends(require_identity)):
    return _maybe_provider(job_summary(list_jobs(identity)))


@router.post("/ai/document-checklist")
def ai_document_checklist(identity: Identity = Depends(require_identity)):
    return _maybe_provider(document_checklist(list_jobs(identity)))


@router.post("/ai/failed-job-diagnosis")
def ai_failed_job_diagnosis(identity: Identity = Depends(require_identity)):
    return _maybe_provider(failed_job_diagnosis(list_jobs(identity)))
