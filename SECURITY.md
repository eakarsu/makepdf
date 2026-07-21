# Security policy

Report vulnerabilities privately to the repository owner; do not attach live
documents, secrets, identity data, or exploit payloads to a public issue.

## Required controls

- Terminate TLS at a maintained reverse proxy and set exact trusted hosts and
  CORS origins.
- Store the API-key pepper, download-signing key ring, bootstrap credential,
  provider credentials, and storage encryption keys in a secret manager.
  Rotate stored API keys through the governance endpoint; overlap download
  signing keys during rotation until prior URLs expire.
- Run API and worker as separate non-root services. Keep the worker network
  disabled and apply seccomp/AppArmor or the platform equivalent in addition
  to the process resource limits.
- Run ClamAV or a compatible scanner with current definitions. Production
  startup fails closed without it.
- Put `/data` and every backup on encrypted, access-controlled storage. SQLite
  does not itself encrypt file contents.
- Alert on readiness failure, 5xx rate, failed/retried jobs, legal-hold changes,
  key rotation, unusual billable usage, and audit export.

Redaction verification proves removal of selected terms and common PDF recovery
channels; it cannot prove that a human selected every sensitive region. Require
two-person visual review for high-impact releases. Optical content that has not
first been OCR'd cannot be selected through text search; use rectangle
redaction and verify the rendered output.

Run `uv run pip-audit`, the locked CI matrix, container scanning, and secret
scanning for every release. Native PDF/OCR libraries must be patched promptly.
