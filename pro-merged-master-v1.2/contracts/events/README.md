# Event contracts

These schemas define queue payloads for the async pipeline.

## Design notes

- Every event has an immutable job envelope.
- Events should be safe to retry.
- Worker implementations should treat event payloads as commands, not authoritative state snapshots.
- Durable status, progress, and error information belong in the `pipeline_jobs` table in Postgres.

## Expected queue progression

1. `ingest_document_job`
2. `classify_document_job`
3. one or more `extract_document_job`
4. one or more `embed_document_job`
5. optional `analyze_documents_job`

Different implementations may collapse or expand these stages, but the stored job ledger should preserve equivalent state transitions.
