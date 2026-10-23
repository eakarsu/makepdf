"""Wave 3C: deterministic AI fallbacks over PDF job records."""
from makepdf.web.routes.wave3c import document_checklist, failed_job_diagnosis, job_summary


def test_job_summary_fallback_preserves_zero_and_false():
    out = job_summary([{"id": "j1", "kind": "merge", "status": "complete", "progress": 100}])
    assert out["aiGenerated"] is False
    assert out["sections"]["metrics"]["failedJobs"] == 0
    assert out["sections"]["metrics"]["hasFailedJobs"] is False


def test_document_checklist_empty_is_not_all_complete():
    out = document_checklist([])
    assert out["sections"]["metrics"]["allComplete"] is False
    assert out["sections"]["metrics"]["totalJobs"] == 0


def test_failed_job_diagnosis_preserves_zero_and_false():
    out = failed_job_diagnosis([{"id": "j1", "kind": "merge", "status": "complete", "attempts": 1}])
    assert out["aiGenerated"] is False
    assert out["sections"]["metrics"]["failedJobs"] == 0
    assert out["sections"]["metrics"]["hasFailedJobs"] is False
    bad = failed_job_diagnosis([{"id": "j2", "kind": "ocr", "status": "failed", "attempts": 2, "stage": "ocr"}])
    assert bad["sections"]["metrics"]["retriedJobs"] == 1
