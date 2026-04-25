# ADR 0000: Phase 0 Baseline Scaffold

Date: 2026-04-24

## Decision

Use the root implementation plans plus `pro-merged-master-v1.2` as the implementation source. Phase 0A-0F establishes the monorepo scaffold, Compose runtime skeleton, idempotent baseline migration wrapper, contract registry, bootstrap auth, protected route conventions, DB-backed job service, and service health surface before product workflows.

## Consequences

- React + Vite is the frontend baseline.
- FastAPI + Pydantic is the API baseline.
- Database and contract files are copied from `pro-merged-master-v1.2`; the only Phase 0 compatibility edit is called out below.
- Baseline migrations are tracked in `structura.schema_migrations`; reruns are no-ops, and legacy Phase 0 databases without the tracking table are adopted by detecting representative existing schema objects.
- The default ParadeDB image is pinned to `paradedb/paradedb:0.21.5-pg17`, matching the PostgreSQL 17 target and avoiding `latest` drift.
- `parties_bm25_idx` preserves the artifact-pack search inputs, with `normalized_name` cast through `pdb.simple` because the pinned ParadeDB build rejects raw `citext` fields inside BM25 indexes.
- Argon2id password credentials, durable session cookies, CSRF protection for state-changing cookie-auth routes, non-production magic-link token return, API-token resolution, contract-style request validation, and configurable cookie names are the Phase 0 auth baseline.
- PGMQ remains the preferred queue transport, but the pinned ParadeDB image does not package `pgmq`. Phase 0 resolves the requested transport profile to the Postgres `pipeline_jobs` ledger with an explicit fallback reason; Redis is fallback-only.
- Retryable failed jobs remain in `pipeline_jobs` and are rescheduled with bounded exponential backoff before workers can claim them again.
- Admin diagnostics and service-health surfaces are represented in the active OpenAPI contract and require an authenticated principal.
- Phase 1 is the next required step: upload, Inbox, and protected viewer.
