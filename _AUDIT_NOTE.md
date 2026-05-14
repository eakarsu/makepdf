# Audit Note — makepdf

**Date**: 2026-05-06
**Bucket**: A. DETECTOR_FALSE_POSITIVE

## Summary

The audit (`_AUDIT/reports/batch_10.md` entry #29) classified this as a
"Python stub" with 0 routes / 0 AI endpoints. That measurement is stale.

The whole-project LLM scan returned multiple genuine hits, and the project
already has a FastAPI web app with a substantial AI surface.

## Files containing LLM references

- `makepdf/web/ai_helpers.py` — shared LLM client + rate limiter + JSON
  parser + SQLite ai_results audit log (`persist_ai_result`,
  `query_ai_results`).
- `makepdf/web/routes/ai_classify.py` — document classification.
- `makepdf/web/routes/smart_redact.py` — AI-assisted redaction.
- `makepdf/web/routes/summarize.py` — document summarization.
- `makepdf/web/routes/ai_form_filler.py` — form-fill autofill.
- `makepdf/web/routes/ai_audit.py` — AI audit feature route.

The web package also contains a full set of non-AI PDF routes (merge,
redact, sign, ocr, ocr_async, optimize, stamp, bates, attach, link, crop,
flatten, metadata, markup, compare, transform, edit, extract, create,
forms).

## Disposition

- **Detector false positive** — project has both real AI endpoints and a
  rich PDF processing surface.

## Audit recommendations applied this batch

Audit batch_10 mentions general gaps already covered by `job_registry.py`
+ `jobs.py` + `ocr_async.py`. Sibling `pdfgenius` (batch_11) lists six
"Custom Feature Suggestions"; #1 (form fill), #2 (classification), #3
(compliance check via `ai_audit`) are already implemented. The remaining
recs (multi-language RAG, white-label SaaS mode, streaming PDF generation)
are NEEDS-PRODUCT-DECISION / TOO-RISKY.

The clear MECHANICAL gap was that `ai_helpers.query_ai_results()` existed
but had no HTTP surface — operators had to query SQLite directly to read
the AI audit log.

### MECHANICAL items implemented

1. **`GET /api/ai-results` endpoint** —
   `makepdf/web/routes/ai_results.py` (new) wires the existing
   `query_ai_results()` helper to a paginated FastAPI route.
   - Filters: `feature` (str), `page` (>=1), `limit` (1..100).
   - Auth: shared `require_api_key` dependency (matches sibling AI routes).
   - Returns `{results, total, page, totalPages}`.
   - Each row exposes feature/model/api_key_hash/input/output/success/
     error_message/latency_ms/created_at — never the raw API key.
   - Registered in `makepdf/web/app.py` next to other AI routers.

## Backlog (deferred, prioritised)

1. **Multi-language RAG** (pdfgenius rec) — would require a vector store
   and an `embed/` route; prototype with sqlite-vss or chromadb.
   NEEDS-PRODUCT-DECISION on storage / cost.
2. **Streaming PDF generation** — websocket / SSE upload progress;
   TOO-RISKY in this batch (substantive infra change).
3. **White-label / multi-tenant** — needs schema changes.
   NEEDS-PRODUCT-DECISION.
4. **Token-cost attribution per API key** — `ai_results` log has feature
   + latency but not token counts; extend `persist_ai_result` to capture
   `prompt_tokens` + `completion_tokens` from OpenRouter responses.
5. **Aggregated stats endpoint** — summarise `ai_results` by feature ×
   day (count, p50/p95 latency, error rate); could close the loop with
   the new GET endpoint.

## Files touched this batch

- `makepdf/web/routes/ai_results.py` — new endpoint exposing the AI audit log.
- `makepdf/web/app.py` — imported and mounted the new router.

## Apply pass 3 (frontend)

- Stack: FastAPI + Jinja2 server-rendered templates (Python). Auth via
  `X-API-Key` header (project-native — there is no JWT layer here, so
  the FE persists the key in browser `localStorage` to mirror the
  "Bearer-from-localStorage" intent).
- Backend AI endpoints (apply-pass-2 + earlier work):
  - `POST /api/classify` (ai_classify.py)
  - `POST /api/summarize` (summarize.py)
  - `POST /api/smart-redact` (smart_redact.py — supports `policy`, `preview`)
  - `POST /api/ai-fill-form` (ai_form_filler.py — supports `preview`)
  - `GET  /api/ai-results` (ai_results.py — already had `/ai-results` HTML page)
- Pre-pass FE state: only the audit log had a UI page. Classify, summarize,
  smart-redact and ai-fill-form had **no FE surface** at all.
- Action: **CREATED-FE** — added a single AI Tools page wiring the four
  endpoints with the existing card / row / btn / alert styling and a
  503 handler (shows the `OPENROUTER_API_KEY not configured` detail).
- Files added / modified:
  - `makepdf/web/templates/ai_tools.html` (new) — UI for the 4 AI features.
  - `makepdf/web/routes/ai_results.py` (extended) — added `GET /ai-tools`
    HTML route on the same router that already serves `/ai-results`, so
    no `app.py` change required (router is already included).
  - `makepdf/web/templates/base.html` — added "AI Tools" nav link.
  - `makepdf/web/templates/index.html` — added "AI Tools" landing card.
- Idempotence: re-running the pass would find the page in place and leave
  it alone (the section above documents what exists).
- Syntax check:
  - `python3 -m py_compile makepdf/web/routes/ai_results.py` &rarr; OK.
  - Jinja2 `env.get_template('ai_tools.html')` &rarr; OK.
  - Inline `<script>` parsed via `node --check`-equivalent &rarr; OK.
- No new dependencies; no `npm install`; no `pip install`.

## Apply pass 4 (mechanical backlog)

Closes backlog item #5 (aggregated stats endpoint).

`aggregate_ai_results()` already existed in `ai_helpers.py` and was
already imported by `routes/ai_results.py` from a previous pass — but
had no HTTP surface, so operators could not see per-feature success
rate / avg-latency without querying SQLite directly. Pure mechanical
gap.

### MECHANICAL items implemented

1. **`GET /api/ai-results/stats` endpoint** — added to existing
   `makepdf/web/routes/ai_results.py` (no `app.py` change — router
   was already mounted). Accepts `days` (1..365, default 7) +
   optional `feature` filter. Reuses the existing `require_api_key`
   dependency. Calls `aggregate_ai_results()` and returns
   `{since, until, days, perFeature:[{feature,count,successCount,
   errorCount,successRate,avgLatencyMs,maxLatencyMs}], totals:{...}}`.

2. **Stats card in `templates/ai_results.html`** — extended the
   existing audit-log page (rather than adding a new page) with a
   "Stats" card: `days` input + "Load stats" button + a feature ×
   {count, OK, Err, success-rate, avg-latency, max-latency} table.
   Reuses the same `X-API-Key` field at the top of the page. Visibly
   handles 503 with "AI is not configured (503): {detail}". Matches
   the page's existing card / row / btn / table styling.

### Backlog (deferred, prioritised)

1. **Multi-language RAG** (pdfgenius rec) — would require a vector
   store and an `embed/` route; prototype with sqlite-vss or
   chromadb. NEEDS-PRODUCT-DECISION on storage / cost.
2. **Streaming PDF generation** — websocket / SSE upload progress;
   TOO-RISKY (substantive infra change).
3. **White-label / multi-tenant** — needs schema changes.
   NEEDS-PRODUCT-DECISION.
4. **Token-cost attribution per API key** — `ai_results` log has
   feature + latency but not token counts; would need
   `persist_ai_result` extended to capture `prompt_tokens` +
   `completion_tokens` from OpenRouter responses (touching every AI
   route). Mechanical follow-up but cross-cutting; deferred.

### Files touched this pass

- `makepdf/web/routes/ai_results.py` — added `GET /api/ai-results/stats`.
- `makepdf/web/templates/ai_results.html` — added Stats card (HTML +
  inline JS).

### Syntax check

- `python3 -m py_compile makepdf/web/routes/ai_results.py` &rarr; OK.
- `Environment(loader=FileSystemLoader(...)).get_template('ai_results.html')` &rarr; OK.
- Inline `<script>` extracted and run through `node --check` &rarr; OK.

No new dependencies; no `npm install`; no `pip install`.
