# Completeness Review: makepdf

**Review date:** 2026-07-18

## Assessment basis

Static inspection of project-owned Python source, configuration, CLI/web routes, PDF operations, and tests only; no package installation, build, OCR/conversion binary execution, external storage/AI call, or runtime launch was performed.

## Classification

**Complete local scope**

The project is a substantial local PDF toolkit with CLI and FastAPI surfaces for creation, merge, extraction, OCR, forms, accessibility, encryption, signing, redaction, comparison, and related operations. Its focused test suite supports local-library completeness, but the web service and security-sensitive transformations require further hardening.

## Why it is not production-ready

- The asynchronous job registry is process-local and explicitly recommends Redis/Celery for multi-process use; jobs and results are not durable across restart or scale-out.
- Uploads are read into memory/temp storage without a complete service-wide quota, malware, parser-sandbox, object-lifecycle, or tenant-isolation design.
- “Redaction” merges opaque overlays; the test named for content removal only checks that an output file exists, so recoverable underlying text/content is not ruled out.
- API-key authentication is a useful baseline but not user/tenant identity, authorization, per-document access, rotation, or audit accountability.
- No checked-in CI/deployment configuration was identified to prove all optional OCR/HTML/native dependencies and cross-platform PDF fixtures.

## Needed features

1. Implement true content-removing redaction and verification that text, images, metadata, incremental revisions, attachments, and recovery paths cannot expose redacted material.
2. Move long jobs to a durable queue with worker isolation, cancellation, retries, idempotency, progress, result/object storage, expiry, and restart recovery.
3. Enforce streaming size/page/time limits, decompression-bomb and malformed-PDF defenses, malware scanning, sandboxed native tools, and secure temp cleanup.
4. Add user/tenant identity, document-level authorization, signed download URLs, key rotation, audit records, retention/legal hold, and deletion propagation.
5. Build CI matrices for core and optional OCR/HTML features with encrypted, malformed, oversized, scanned, multilingual, signed, and redaction-adversarial fixtures.
6. If exposed as SaaS, add quotas/billing, observability, backup/restore, dependency vulnerability monitoring, and a documented privacy/data-processing boundary for AI/cloud routes.

## Risks or launch blockers

- Visual overlays are not sufficient evidence of secure redaction and could leak highly sensitive content.
- In-process jobs and temporary result paths can disappear or become inconsistent during restart or multi-worker deployment.
- PDF and OCR parsers process attacker-controlled complex files and need isolation and resource limits.
- A single shared API key cannot safely isolate documents or attribute actions in a multi-user service.

## Evidence inspected

- `pyproject.toml`
- `makepdf/core/redaction.py:315`
- `tests/test_redaction.py:32`
- `makepdf/web/job_registry.py:13`
- `makepdf/web/auth.py:22`
- `makepdf/web/routes/ocr_async.py:28`

## Recommended next action

Before expanding formats or AI tools, replace overlay-only redaction with verified content removal and move one OCR job path onto a durable, isolated queue with strict upload limits and adversarial tests.

## Implementation progress (2026-07-19)

1. Replaced overlay-only redaction with PyMuPDF native content redaction and a fresh, non-incremental, garbage-collected save. Intersecting text, raster/vector content, metadata, XML, attachments, JavaScript, thumbnails, hidden text, and orphaned objects are removed; verification checks extracted text, raw bytes, embedded files, incremental revisions, and recovery markers. Signed inputs fail closed for an explicit re-signing workflow. Adversarial tests cover metadata and attachment recovery, incremental history, embedded-image removal, multilingual text, and signed-input refusal.
2. Replaced the process-local registry with a SQLite WAL durable queue using transactional claims, leases and stale-job recovery, bounded retries/backoff, idempotency conflict detection, progress, cancellation, result checksums, expiry, persisted worker heartbeats, and hash-chained audit events. OCR uploads and results survive API restart, and work executes in a separate resource-limited subprocess with timeout and cancellation enforcement.
3. Centralized service intake now streams into mode-0600 quarantine files with byte, page, object, decoded-pixel, decompression-ratio, and time budgets. PDF/image parsing runs in a constrained child probe, native OCR runs in an isolated worker, ClamAV can fail closed, HTML creation rejects external/local resource fetches, cloud imports reject redirects and private-network destinations, and temporary artifacts receive lifecycle cleanup. Legacy synchronous transformations return HTTP 410 in production so complex parsing cannot run in the API process.
4. Added persistent, pepper-hashed, rotating API keys with tenant, user, and administrator/operator/auditor roles; document ownership checks; rotating-key signed five-minute download URLs; append-only tenant audit; configurable retention; legal holds; and deletion propagation across source, result, and queued work. Production configuration fails closed when identity or signing material is unsafe.
5. Added Linux CI matrices for Python 3.10/3.13 core behavior and actual OCR/HTML optional dependencies, malformed/encrypted/oversized and recovery-path fixtures, dependency and secret scanning, locked dependencies, and reproducible sdist/wheel creation. Package metadata now includes all web templates and static assets, verified directly in the built wheel.
6. Added tenant quotas, immutable daily billing-usage snapshots, request/latency metrics, health/readiness checks, online SQLite backup plus integrity/audit-chain restore verification, non-root container/Compose deployment, safe check/start/backup scripts, provider egress gates, and security/privacy/operations documentation. AI and cloud transfer require explicit production enablement, HTTPS allowlists, and recorded data-processing approval.

Verification passed with all 161 tests, including real installed native OCR/Poppler worker execution and optional HTML generation; focused Ruff checks; sdist/wheel build with packaged asset inspection; `pip-audit` with no known vulnerabilities; Gitleaks with no leaks; Compose rendering; shell syntax; and `git diff --check`.

External launch dependencies remain explicit rather than simulated: production IdP and KMS/secret provisioning, encrypted managed storage and backup infrastructure, operated ClamAV and monitoring/on-call, provider credentials and contractual/DPA approvals, a witnessed restore exercise, and independent security, privacy, and accessibility review.

## Runtime acceptance (2026-07-20)

The root launcher now defaults to the API service, selects the project `.venv`, requires a free numeric assigned port, and binds only to loopback. Non-production acceptance derives an isolated data/object store and an environment-bootstrap tenant administrator API key from the validator's ephemeral credential; production remains governed by the existing fail-closed identity, signing-key, storage, and malware-scanner checks. On isolated ports 55672/6150/6151, configuration validation and startup succeeded, the key authenticated the declared `X-API-Key` identity boundary, and the protected `/metrics` API succeeded (`API_VERIFIED`, `startup_login_session_api`). The full project-environment suite passed 161 tests, focused Ruff checks passed, and launcher syntax plus `git diff --check` passed. A system-Python collection attempt lacked PyMuPDF; it made no source change and was superseded by the successful project-venv run.
