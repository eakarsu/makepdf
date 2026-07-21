# Privacy and data-processing boundary

By default MakePDF processes files on the configured host. Uploaded documents,
job parameters, results, ownership metadata, checksums, and audit events remain
on the configured service volume until their retention deadline or an allowed
deletion request. Legal hold prevents deletion. Audit evidence and immutable
daily usage statements intentionally outlive deleted document bytes.

External AI and cloud processing are disabled by default. Enabling OpenRouter
requires `MAKEPDF_ALLOW_EXTERNAL_AI=true`, provider credentials, and an internal
DPA/reference identifier. Text sent to that provider may contain personal or
regulated data; the operator must establish purpose, consent, residency,
retention, subprocessors, incident terms, and deletion obligations. Cloud URLs
must be on an explicit hostname allowlist. MakePDF does not claim HIPAA, GDPR,
PCI, legal-discovery, or other certification by itself.

The application records document content digests rather than document content
in audit and billing records. It does not put raw API keys in those records.
Provider error bodies are not returned to users by the native worker. Operators
must keep application logs free of PDF text and request bodies.
