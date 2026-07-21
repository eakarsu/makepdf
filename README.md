# MakePDF

MakePDF is a Python PDF toolkit with CLI and FastAPI surfaces. The supported
web-service path uses verified irreversible redaction, bounded streaming
intake, tenant/user identity, durable local jobs, isolated OCR workers,
retention/legal hold, immutable auditing, and signed result downloads.

## Local library

```sh
uv sync --extra dev
uv run pytest -q
uv run makepdf --help
```

Secure redaction requires PyMuPDF and writes a fresh non-incremental file. It
removes intersecting text, raster images, and vector graphics; scrubs metadata,
XML metadata, attachments, JavaScript, thumbnails, hidden text, and orphaned
objects; then verifies extraction, bytes, attachments, and revision markers.
Signed inputs are refused because a transformation would invalidate their
signature and must go through an approved re-signing workflow.

## Production service

Copy `.env.example` to an external secret source and replace every placeholder.
Do not commit the resulting environment. Startup never installs packages,
creates users, resets data, or weakens validation.

```sh
./start.sh check
./start.sh api
./start.sh worker
```

The API and worker share a SQLite WAL database and object directory on one
durable encrypted host volume. Atomic claims and leases support multiple API
and worker processes on that host. SQLite on a network filesystem and a
multi-node cluster are outside this boundary; use a supported shared
transactional database/queue before scaling across hosts.

Long OCR requests require an `X-API-Key` tenant-user credential and an
`Idempotency-Key`. The API streams and validates the upload, records document
ownership, and enqueues it. A no-network, non-root worker with CPU, memory,
file-size, process, descriptor, and wall-clock limits performs the native OCR.
Results are checksum-addressed and downloaded through a tenant authorization
check or a five-minute signed URL. Cancellation, retry/backoff, restart lease
recovery, progress, expiration, and deletion propagation are persisted.

Production readiness is exposed at `/ready`; liveness is `/health`; authenticated
Prometheus-format process metrics are `/metrics`. `/api/governance` exposes
key rotation, audit reads, legal holds, deletion, and immutable daily usage
exports. The bootstrap environment key should only create rotating stored keys,
then be removed in favor of the organization's credential lifecycle.

## Security boundaries

Production only exposes durable mutation APIs under `/api/ocr/`, `/api/jobs/`,
`/api/governance/`, and `/api/cloud-storage/`. Legacy synchronous web
transformations remain available for local use but return HTTP 410 in production,
so untrusted parsing and long-running transformations cannot execute in the API
process.

- Malware scanning is fail-closed in production. Scanner outages make intake
  unavailable rather than silently accepting content.
- All service upload helpers use the streaming intake boundary. Synchronous
  native OCR endpoints return `410`; the durable isolated worker is required.
- HTML rendering rejects local and external resource URLs. Cloud imports use
  HTTPS hostname allowlists, DNS/private-address rejection, no redirects, and
  the normal bounded PDF intake.
- External AI and cloud routes are disabled unless explicitly enabled.
  Production AI enablement also requires a recorded DPA reference.
- The service database and objects contain sensitive plaintext unless the
  deployment volume provides encryption at rest. Key custody and KMS-backed
  storage are deployment responsibilities.

See [SECURITY.md](SECURITY.md), [OPERATIONS.md](OPERATIONS.md), and
[PRIVACY.md](PRIVACY.md) before operating the web service.
