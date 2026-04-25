# Structura

Structura is a local-first document workbench for preserving original document bytes, deriving structural artifacts, extracting evidence-backed facts, and making a private corpus searchable and reviewable.

This repository is now implemented through Phase 0A-0F:

- React + Vite web placeholder in `apps/web`
- FastAPI API in `apps/api` with health, contract, auth/session, protected document/asset, job, and admin health routes
- worker and model placeholder modules with HTTP health checks
- shared Python libraries under `lib`
- baseline contracts copied to `contracts`
- baseline SQL copied to `database`
- ZFS infrastructure copied to `infrastructure/zfs`
- Docker Compose runtime skeleton
- idempotent migration and contract validation helpers
- bootstrap admin CLI, Argon2id password credentials, durable DB-backed sessions, configurable session/CSRF cookies, magic-link scaffolding, and protected route dependencies
- Postgres-backed `pipeline_jobs` service with bounded retry scheduling plus service-health snapshots for default workers

The next implementation slice starts at Phase 1: upload, Inbox, and protected viewer.

## Local Commands

```bash
make bootstrap
make test
make contracts
make api-dev
make web-dev
```

Docker Compose:

```bash
docker compose up postgres api web
```

The default Postgres image is pinned to `paradedb/paradedb:0.21.5-pg17` to match the Phase 0 PostgreSQL 17 baseline. Do not use `latest` unless the mount strategy and extension compatibility have been reviewed.

Model placeholders are behind a profile:

```bash
docker compose --profile models up model-qwen model-granite model-embed
```

Redis is fallback-only:

```bash
docker compose --profile redis-fallback up redis
```

PGMQ remains the preferred queue transport for later phases, but the pinned ParadeDB image used for Phase 0 does not package `pgmq`. The Phase 0 job service resolves that requested profile to the durable `pipeline_jobs` ledger, records the fallback reason in code, and keeps Redis behind an explicit fallback profile.

## Runtime Roots

The target deployment uses `/srv/structura`. For local development on a workstation without that path, override:

```bash
STRUCTURA_RUNTIME_ROOT=.runtime docker compose up postgres api web
```

## Migration Baseline

The baseline migration runner applies:

1. `database/001_extensions.sql`
2. `database/010_types_and_enums.sql`
3. `database/020_core_tables.sql`
4. `database/025_baseline_identity_acl_candidate_rules.sql`
5. `database/030_constraints_and_triggers.sql`
6. `database/040_indexes_bm25_pgvector.sql`
7. `database/050_views_and_functions.sql`
8. `database/060_seed_taxonomies.sql`

`database/070_query_examples.sql` is intentionally excluded from default migration execution.

Applied migrations are tracked in `structura.schema_migrations`. If an older Phase 0 database already has the baseline schema but no tracking table, the runner detects the existing legacy objects, records the matching baseline scripts, and subsequent runs become no-ops.

Admin diagnostics such as `/api/v1/migrations/baseline` and `/api/v1/admin/service-health` are protected by the same session/API-token principal dependency used by Phase 0 product skeleton routes.
