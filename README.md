# Structura

Structura is a local-first document workbench for preserving original document bytes, deriving structural artifacts, extracting evidence-backed facts, and making a private corpus searchable and reviewable.

This repository is now implemented through Phase 8 with the Phase 8.5 model-runtime
foundation in progress:

- React + Vite web app in `apps/web`
- FastAPI API in `apps/api` with health, contract, auth/session, protected document/asset, job, admin health, and organization routes
- ingest, preview, Docling, extraction, text/visual embedding, watched-folder, and relationship workers plus remaining later-phase/model placeholders with HTTP health checks
- shared Python libraries under `lib`
- baseline contracts copied to `contracts`
- baseline SQL copied to `database`
- ZFS infrastructure copied to `infrastructure/zfs`
- Docker Compose runtime skeleton
- idempotent migration and contract validation helpers
- bootstrap admin CLI, Argon2id password credentials, durable DB-backed sessions, configurable session/CSRF cookies, magic-link scaffolding, and protected route dependencies
- Postgres-backed `pipeline_jobs` service with household-scoped job visibility, bounded retry scheduling, manual retry recovery, and service-health snapshots for default workers
- Phase 1 upload, Inbox, protected asset viewer, content-addressed immutable storage, and preview fallback generation
- Phase 2 manual folders, tags, document filing, primary folder selection, metadata edits, folder filtering, and audit events
- Phase 3 Docling canonical parse artifacts, page/element/table/chunk persistence, page preview assets, and protected parse-debug diagnostics
- Phase 4 document classification, deterministic extraction gateway, receipt/invoice/EOB typed candidates, canonical fact promotion, review task/action APIs, and Review Queue UI
- Phase 5 lexical, semantic, and hybrid corpus search; search projection refresh; deterministic text embeddings; embedding worker; facets; saved searches; smart-folder execution; and Corpus Search UI
- Phase 6 contacts, aliases, document-contact links, duplicate merge suggestions, watched-folder PDF intake, filing rules, dry-run explanations, reviewable filing suggestions, operator maintenance CLI commands, and Automation Workbench UI
- Phase 7 document relationships, relationship suggestions, accept/reject review actions, relationship worker, related-document Viewer panel, timelines, deadlines, relationship/deadline search filters, smart views, and Relationships/Timelines UI
- Phase 8 difficult-document quality detection, review-required uncertainty, selective fixture visual byte embeddings, Qwen-eligible handwriting fallback with honest Docling provenance until live mode is enabled, visual/hybrid retrieval policy, and difficult-document Viewer/Search/Review cues
- Phase 8.5 model runtime profiles, bounded internal model HTTP clients, Qwen/Granite/text/visual model adapters, fixture-vs-live mode separation, model service health snapshots, and model-corpus gate scaffolding

## Local Commands

```bash
make bootstrap
make test
make integration-test
make contracts
make golden-corpus
make api-dev
make web-dev
```

Docker Compose:

```bash
docker compose up postgres api web
```

The default Postgres image is pinned to `paradedb/paradedb:0.21.5-pg17` to match the Phase 0 PostgreSQL 17 baseline. Do not use `latest` unless the mount strategy and extension compatibility have been reviewed.

Python runtime and validation dependencies are locked for Linux in `apps/api/requirements.lock`, `workers/docling/requirements.lock`, and `requirements-dev.lock`. Regenerate them intentionally with `uv pip compile --python-platform linux ...` during dependency update work rather than allowing CI or Docker builds to resolve open-ended ranges.

For phase gates, the GPU node is canonical. Push the repo, pull it at `/tank/repos/structura` on `bgconley@10.25.0.50`, use `/tank/venvs/structura` for Python validation, and use pinned container images for web lint/build rather than host Node/npm. Live Playwright tests should target the GPU-hosted web service with:

```bash
STRUCTURA_E2E_LIVE=1 npx playwright test tests/e2e/phase1-live.spec.ts tests/e2e/phase2-live.spec.ts tests/e2e/phase3-live.spec.ts tests/e2e/phase4-live.spec.ts tests/e2e/phase5-live.spec.ts tests/e2e/phase6-live.spec.ts tests/e2e/phase7-live.spec.ts tests/e2e/phase8-live.spec.ts --workers=1
```

Use `make integration-test` for DB-backed integration validation. It creates a disposable migrated database from `STRUCTURA_INTEGRATION_BASE_DATABASE_URL`, runs `tests/integration`, and drops the database afterward so test fixtures do not pollute the canonical runtime DB.

Use `make golden-corpus` for the sanitized deterministic benchmark manifest. Use `python scripts/run_golden_corpus.py --require-model-backed --manifest <path>` for model-backed release-candidate corpus evidence once real model adapters are configured. Use `make backup-restore-rehearsal` with `STRUCTURA_INTEGRATION_BASE_DATABASE_URL` to run a disposable PostgreSQL migration/restore rehearsal.

Model placeholders are behind a separate profile. They are health placeholders only; they do not provide Qwen, Granite, or embedding inference:

```bash
docker compose --profile models-placeholder up model-qwen-placeholder model-granite-placeholder model-embed-placeholder model-vl-embed-placeholder
```

Live Phase 8.5 model services are behind explicit profiles and require approved pinned images plus `STRUCTURA_MODEL_MODE=live`:

```bash
docker compose --profile models-live up model-qwen model-granite model-embed
docker compose --profile visual-embed-live up model-vl-embed
```

Run deterministic model-corpus shape validation with:

```bash
make model-corpus
```

Release-candidate model evidence must use a private model-backed manifest:

```bash
python scripts/run_model_corpus.py --require-model-backed --manifest tests/fixtures/model_corpus/phase8_5_model_manifest.json
```

Search indexing workers are behind the search profile:

```bash
docker compose --profile search up worker-embeddings
```

Visual embedding workers are behind the visual profile:

```bash
docker compose --profile visual up worker-visual-embeddings
```

Watched-folder intake is behind the automation profile:

```bash
docker compose --profile automation up worker-watched-folders
```

Relationship suggestions and deadline refreshes are behind the relationships profile:

```bash
docker compose --profile relationships up worker-relationships
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
9. `database/065_pipeline_jobs_household_scope.sql`
10. `database/066_folder_household_uniqueness.sql`
11. `database/067_document_read_acl_function.sql`
12. `database/068_phase4_extraction_review.sql`
13. `database/069_phase5_search.sql`
14. `database/071_phase5_search_guardrails.sql`
15. `database/072_phase6_automation.sql`
16. `database/073_phase7_relationships.sql`
17. `database/074_phase7_deadline_status_waived.sql`

`database/070_query_examples.sql` is intentionally excluded from default migration execution.

Applied migrations are tracked in `structura.schema_migrations`. If an older Phase 0 database already has the baseline schema but no tracking table, the runner detects the existing legacy objects, records the matching baseline scripts, and subsequent runs become no-ops.

Admin diagnostics such as `/api/v1/migrations/baseline` and `/api/v1/admin/service-health` are protected by the same session/API-token principal dependency used by Phase 0 product skeleton routes.
