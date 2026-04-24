# 15 — PGMQ and Worker Strategy

Historical note: In v1.3 this document is background rationale unless explicitly referenced by the ADR summary or the current normalization doc.

Prepared: 2026-04-23

## 1. Decision

Use a Postgres-native queue using PGMQ as the normative v1.3 transport profile. If the selected Postgres/ParadeDB image cannot install or operate the extension cleanly, fall back to Redis/RQ/Dramatiq without changing the durable `pipeline_jobs` ledger.

Keep the existing durable `pipeline_jobs` ledger concept even if PGMQ is used. PGMQ should carry queue messages; business state remains in ordinary application tables.

## 2. Why this improves the previous bundle

The previous bundle assumed Redis-backed queues plus durable job state in Postgres. That is workable, but it means:
- one more runtime dependency;
- one more backup/restore consideration;
- more split-brain risk between queue state and job state;
- more operational complexity on a single workstation.

PGMQ is attractive because:
- the app is already Postgres-centered;
- the deployment is single-node and local-first;
- job messages can live close to the durable pipeline ledger;
- dead-letter and retry behavior can be observed through SQL/admin surfaces.

## 3. Guardrails

Do not allow the queue to become business truth.

Queue messages should contain:
- job ID;
- document ID;
- requested stage;
- priority;
- idempotency key;
- trace/correlation ID.

Queue messages should not contain:
- raw document text;
- raw model output;
- sensitive extracted fields;
- large payloads;
- prompt bodies with embedded document content.

## 4. Recommended hybrid design

Use both:

### PGMQ message

Small durable scheduling message.

### `pipeline_jobs` row

Application-level job ledger with:
- status;
- attempt count;
- max attempts;
- run IDs;
- document ID;
- stage;
- result/error JSON;
- auditability.

This keeps queue mechanics separate from application semantics.

## 5. Fallback strategy

If PGMQ is unavailable or painful in the chosen Postgres image:

1. Keep `pipeline_jobs`.
2. Use Redis/RQ/Dramatiq for queue signaling.
3. Treat Redis as non-canonical.
4. Recover pending jobs from Postgres on restart.

This fallback is acceptable and should not block product progress.

## 6. Worker stages

Recommended stage names:
- `ingest.preflight`
- `document.preview`
- `docling.convert`
- `document.classify`
- `extract.qwen`
- `extract.granite`
- `extract.normalize`
- `canonicalize.merge`
- `review.generate_tasks`
- `search.chunk`
- `search.embed`
- `relationships.suggest`
- `analysis.run`
- `export.bundle`

## 7. Dead-letter behavior

A job moves to dead-letter when:
- max attempts exceeded;
- deterministic validation impossible;
- required input asset missing;
- model endpoint repeatedly unavailable;
- migration/schema mismatch discovered.

Dead-letter jobs should appear in the Admin/Status surface with:
- document link;
- stage;
- error class;
- last error;
- retry button;
- suppress/dismiss button.

## 8. Concurrency

Start conservative:
- 1 Docling worker
- 1 VLM extraction worker per GPU-bound model service
- 1 embedding worker
- 1 lightweight relationship/rules worker

Make concurrency environment-configurable.

## 9. Launch requirement

v1 is not ready unless:
- queued/running/failed/dead-letter counts are visible;
- stuck jobs can be retried;
- job retries do not overwrite canonical history;
- queue messages do not leak sensitive content.
