# Structura

Structura is a local-first document workbench for preserving original document bytes, deriving structural artifacts, extracting evidence-backed facts, and making a private corpus searchable and reviewable.

This repository is now implemented through Phase 8 with the Phase 8.5 semantic
annotation/model-runtime foundation in progress:

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
- Phase 8.5 semantic annotation manifests, Qwen3-VL-8B Smart Parse semantic planning on `model-qwen-semantic`, extractive-first text lanes, Qwen vision fallback for exceptional difficult pages, semantic worker/runtime profile, bounded internal model HTTP clients, fixture-vs-live mode separation, model service health snapshots, and model-corpus gate scaffolding

## Production Completion

The [September 2026 readiness review](docs/reviews/2026-09-07-production-readiness-review.md) assesses the current project as an engineering beta, with substantial tested foundations and unresolved product, integrity, model-quality and operational gates. Use the [production completion plan](STRUCTURA_PRODUCTION_COMPLETION_PLAN.md), [execution strategy](docs/plans/production-completion/execution.md) and [closure register](docs/plans/production-completion/closure-register.md) to finish the application against the spec and all 26 stories. The root implementation plan remains the phase map.

The selected ingestion model is **Qwen3.8-27B BF16, already running on Oxcart**, under [ADR 0008](docs/adr/0008-qwen38-27b-ingestion.md). This is an accepted plan decision; the existing 8B application profiles still require adapter/schema/provenance migration and authenticated validation. Blackbird's available PRO 4000 is proposed for dedicated text/visual retrieval embeddings. The [topology ADR](docs/adr/0007-blackbird-production-validation-topology.md) requires measured concurrent ingestion/search capacity and protection of existing Oxcart clients. Existing GPU scripts need target/ownership guards before use; do not recreate the resident 27B service as routine Structura setup.

The accepted target is **Qwen-native full-document parsing and extraction** under [ADR 0009](docs/adr/0009-qwen-native-document-parsing.md), with lightweight source-page handling and a complete versioned searchable parse. Docling remains temporary migration/comparison support. Blackbird's embedding role covers document/chunk/page ingestion and reindexing as well as query encoding. Implementation must preserve original evidence, historical artifacts and human corrections, and pass end-to-end gates with Docling disabled. The implemented feature list above describes the current code, which still needs this migration.

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

Use `make golden-corpus` for the sanitized deterministic benchmark manifest. Use `make model-corpus-release MODEL_CORPUS_RELEASE_MANIFEST=<path>` or `python scripts/run_model_corpus.py --require-model-backed --manifest <path>` for model-backed release-candidate corpus evidence once real model adapters are configured. Use `make backup-restore-rehearsal` with `STRUCTURA_INTEGRATION_BASE_DATABASE_URL` to run a disposable PostgreSQL migration/restore rehearsal.

Model placeholders are behind a separate profile. They are health placeholders only; they do not provide Granite or embedding inference:

```bash
docker compose --profile models-placeholder up model-granite-placeholder model-embed-placeholder model-vl-embed-placeholder
```

The following describes the pre-migration implementation, not the selected 27B deployment. Use the completion execution strategy to integrate the existing Oxcart endpoint; the managed smoke command below must be adapted before it can validate the new topology.

Live Phase 8.5 model services are behind explicit profiles. Compose defaults use
`voipmonitor/vllm:cu130` for Qwen Smart Parse/Qwen vision fallback and visual
embedding services, and TEI CUDA for on-demand/offload text embeddings; release
candidates still need digest-pinned image evidence. Granite is no longer part of the default required live runtime; start the explicit `granite-live` profile only for rollback or comparison gates.

```bash
STRUCTURA_MODEL_MODE=live \
STRUCTURA_MODEL_SMOKE_MANAGE_COMPOSE=1 \
bash scripts/gpu/phase8_5_model_smoke.sh
```

Semantic annotation workers are behind the semantic/extraction profile. They consume
Docling-grounded page images and route targeted extractive-first text or Qwen
vision fallback jobs:

```bash
docker compose --profile semantic up worker-semantic-annotations
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

## Upload Cleanup Runtime

`worker-upload-cleanup` owns expiry and byte reclamation for durable upload attempts.
It is a CPU-only core Compose service using the API image, UID and runtime group,
with the exact same canonical storage mount. Upload staging lives inside that
mount so source/publication hardlinks share a filesystem. Provision and verify the
correct mount before starting it; a database name check cannot establish storage
provenance. The private staging directory is owner-only. Keep API and cleanup on
the same image UID, and preserve every `.upload-attempts/*.lock` file: replacing a
lock inode can let a late writer escape cleanup exclusion.

After migration `104_completion_upload_attempts.sql` is applied, start or update
only this service with:

```bash
docker compose up -d --no-deps --build worker-upload-cleanup
```

This command does not start model services. Compose shares the upload policy
environment between API and maintenance. The worker requires explicit
`STRUCTURA_DATABASE_URL`, `STRUCTURA_RUNTIME_ROOT` and
`STRUCTURA_UPLOAD_CLEANUP_EXPECTED_DATABASE`; it checks the resolved libpq name,
actual connected database and migration marker before any cleanup mutation.
Provisioning remains responsible for matching this database to its canonical
mount. Maintenance never creates/chmods missing directories: it requires the
canonical root and owner-only `.upload-attempts` directory to exist, rejects
symlinks, and verifies their device/inode before claims and after lock acquisition.
An empty installation returns 503 until the API initializes its upload namespace.
After verifying the API mount and UID, initialization without an upload is explicit:

```bash
docker compose exec api python -c 'from lib.uploads.service import UploadService; UploadService()'
```

The next maintenance sweep opens that existing namespace. An already-running
worker rejects directory replacement and preserves reservations; it never silently
adopts an empty replacement. This is not a durable DB-to-filesystem UUID binding.

The initial sweep runs immediately. Configurable defaults are a 15-second interval,
at most 100 inactive operations plus 100 transfer candidates per sweep, and a
20-second soft work budget checked between transfers. Expired/live IO remains
reserved until the exact stable source lock is acquired, all transfer-owned links
are durably removed or retained by a real document reference, and cleanup is
confirmed in SQL. The worker skips currently owned cleanup claims, prioritizes
never-attempted rows, then rotates older cleanup attempts ahead of newer ones.
Source conflicts and storage failures retain reservations and do not stop the
remaining batch. Database failures stop new claims; failed sweeps back off to
15/30/60/120 seconds, resetting after a successful sweep. These are validation
defaults, not throughput or latency guarantees.

The loopback-only health listener uses port 8211 with no published port.
`/livez` reports process liveness; `/healthz` reports 503 while starting, degraded,
stopping or without progress for 90 seconds. Its response uses in-memory progress,
not request-time SQL or filesystem probes. Sweep logs and persisted service-health
records contain only bounded counts and static error categories, never source
paths, filenames, credentials or raw exceptions. DB connect/query/lock waits are
bounded at 5/5/3 seconds. A filesystem call can still stall; health turns stale
and ownership is retained rather than abandoning IO.

For one bounded operator sweep against the already configured service:

```bash
docker compose exec worker-upload-cleanup python -m workers.upload_cleanup.worker --once
```

SIGTERM/INT stops new claims and allows the currently owned transfer to finish.
Compose provides a 30-second stop grace; a forced kill leaves the byte reservation
and expiring cleanup claim for restart. `restart: unless-stopped` restarts process
failures; Docker does not automatically restart an unhealthy but running process.
Investigate the static health category and mount/DB availability, then restart only
`worker-upload-cleanup` if necessary. Do not manually delete staging or release
reservations to clear a stuck upload. Persistent source-identity conflicts require
operator investigation. Root-owned deployment validation must run the separate
process/DB recovery tests and confirm the configured service's health. Those tests
and fsync ordering do not constitute a host power-loss recovery rehearsal.

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
18. `database/075_phase8_5_semantic_annotations.sql`
19. `database/076_phase8_5_visual_embedding_2048.sql`

`database/070_query_examples.sql` is intentionally excluded from default migration execution.

Applied migrations are tracked in `structura.schema_migrations`. If an older Phase 0 database already has the baseline schema but no tracking table, the runner detects the existing legacy objects, records the matching baseline scripts, and subsequent runs become no-ops.

Admin diagnostics such as `/api/v1/migrations/baseline` and `/api/v1/admin/service-health` are protected by the same session/API-token principal dependency used by Phase 0 product skeleton routes.
