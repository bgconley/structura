# Structura End-To-End Implementation Plan

Last updated: 2026-04-24

This is the working canonical implementation plan for Structura. It is derived from `pro-merged-master-v1.2/`, with the user's clarification that Markdown files are the default working source for duplicate artifact pairs so long as there is no material Markdown/DOCX drift.

## Non-Negotiable Product Rules

- Structura is a local-first document workbench, not a generic PDF chatbot.
- Original uploaded bytes are immutable and remain the document source of truth.
- Docling canonical artifacts, page records, element records, chunks, previews, and model artifacts are structural derivatives.
- `canonical_fields` and `canonical_line_items` are the default accepted-fact read model for UI, filtering, filing, search enrichment, and export.
- Candidate tables remain review inputs and provenance records.
- Trusted extracted values require evidence with page number plus a concrete locator: bounding box, element id, table row, text span, or source excerpt.
- No accepted typed extraction may be persisted without schema validation.
- Low-confidence, validation-failing, or weak-evidence extraction paths must create review tasks.
- Analysis is optional, citation-backed, and separate from canonical facts.
- No direct object-store URI should be exposed to the browser; assets are served through authorized API routes.
- PGMQ is the preferred queue transport, but `pipeline_jobs` remains the durable application ledger. Redis is fallback only.

## Source References

Artifact pack:

```text
pro-merged-master-v1.2/
```

Primary technical sources:

```text
AGENT_START_HERE.md
docs/01_App_Specification.md
docs/01_App_Specification.docx
docs/02_Phased_Implementation_Plan.md
docs/02_Phased_Implementation_Plan.docx
docs/03_Agent_Bootstrap_and_Execution_Order.md
docs/04_User_Stories_and_Acceptance_Criteria.md
docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md
docs/06_Testing_QA_and_Release_Strategy.md
docs/07_Repository_Layout_and_Coding_Standards.md
docs/08_ZFS_Datasets_and_Storage_Plan.md
docs/09_Deployment_and_Runtime_Architecture.md
docs/10_Architectural_Decision_Record_Summary.md
docs/11_Model_Routing_and_Output_Contracts.md
docs/21_v1.3_Normalization_and_Design_Language.md
database/
contracts/
infrastructure/
```

UI sources are defined in `STRUCTURA_UI_FIGMA_QA_PLAN.md`.

## Source Alignment And Conflict Rules

Markdown files are the default working source for duplicate artifact pairs in this repo. The stale artifact-pack note that DOCX files are convenience exports must not be used to ignore Word-document content, but the duplicate DOCX files do not need to be re-read by default when the corresponding Markdown file exists and no material drift is known.

Current parity note:

- `docs/01_App_Specification.md` and `docs/01_App_Specification.docx` were spot-checked on 2026-04-24 and no material content differences were found.
- `docs/02_Phased_Implementation_Plan.md` and `docs/02_Phased_Implementation_Plan.docx` were spot-checked on 2026-04-24 and no material content differences were found.

Use the DOCX file only when:

- the user explicitly asks for layout/fidelity review;
- the Markdown file is missing or appears incomplete;
- a material Markdown/DOCX mismatch is suspected and needs verification.

For non-UI conflicts, use this order:

1. User clarifications made after the artifact pack.
2. Materially aligned Markdown and DOCX artifact content, with Markdown as the default working read.
3. `docs/10_Architectural_Decision_Record_Summary.md`.
4. `docs/21_v1.3_Normalization_and_Design_Language.md`.
5. `database/*.sql` in documented apply order.
6. `contracts/api/openapi.yaml`.
7. `contracts/schemas/*.json` and `contracts/events/*.json`.
8. Remaining docs as rationale and context.

If Markdown and DOCX versions conflict materially, stop and ask the user. Do not silently resolve it.

For UI conflicts, defer to `STRUCTURA_UI_FIGMA_QA_PLAN.md`.

## Environment Assumptions

Target runtime from the artifact pack:

- Ubuntu 24.04 on Lenovo P620.
- AMD Threadripper Pro 3975WX, 128 GB RAM.
- Two NVIDIA RTX Pro 4000 Blackwell GPUs, 24 GB each.
- ZFS pool mounted under `/srv/structura`.
- Docker Compose first; k3s deferred.
- Local-first default with no external model API calls in critical flows.

Implementation should still run in a local development profile on this workstation before final host deployment. Any divergence from the target runtime should be recorded as an ADR update.

## GPU Node Development Sync Policy

The application will live on the GPU node at `10.25.0.50`.

Required access and paths:

```text
SSH user: bgconley
SSH key: /Users/brennanconley/vibecode/infx/ubuntu24_ed25519
Repo checkout: /tank/repos/structura
Virtualenv root: /tank/venvs
Remote git URL: https://github.com/bgconley/structura.git
```

Operational rule:

- After every local commit and push to GitHub, immediately SSH to the GPU node and pull the updated repository.
- If `/tank/repos/structura` does not exist, create `/tank/repos` as needed and clone `https://github.com/bgconley/structura.git` into `/tank/repos/structura`.
- Do not create application virtual environments inside the repo checkout. Put them under `/tank/venvs`.
- For database, object storage, derived artifacts, exports, staging, cache, models, logs, backups, and observability data, follow the artifact ZFS plan rather than inventing new locations.

Required sync command shape:

```bash
ssh -i /Users/brennanconley/vibecode/infx/ubuntu24_ed25519 bgconley@10.25.0.50 '<clone-or-pull commands>'
```

## Artifact Alignment Matrix

This plan intentionally covers the artifact surfaces as follows:

| Artifact surface | Covered in this plan |
| --- | --- |
| `AGENT_START_HERE.md` non-negotiables and gates | Non-negotiable rules, Phase 0-5 gates, milestone mapping below |
| `01_App_Specification` | Product principles, functional phases, nonfunctional gates |
| `02_Phased_Implementation_Plan` | Phase structure and sequencing |
| `03_Agent_Bootstrap_and_Execution_Order` | Phase 0/1 build order and worker/API sequencing |
| `04_User_Stories_and_Acceptance_Criteria` | Phase deliverables and release gate |
| `05_Nonfunctional...` | Auth, privacy, observability, backup, failure handling, performance checks |
| `06_Testing_QA...` | Golden corpus, Playwright UI QA, migration/restore tests |
| `07_Repository_Layout...` | Monorepo scaffold and coding standards |
| `08_ZFS...` and infrastructure CSV/scripts | Runtime mounts and storage plan |
| `09_Deployment...` | Compose service topology and model-server placement |
| `10_ADR...` | Architectural defaults and candidate/canonical/read-model rules |
| `11_Model_Routing...` | Docling/Granite/Qwen routing and output contracts |
| `12_Risk Register...` | Open decisions and revisit triggers below |
| `13-20 addenda` | Candidate/canonical, PGMQ, auth/ACL, contacts/rules, filter-aware search, normalization |
| `21_v1.3...` | Structura namespace, evidence, protected assets, design language |
| `database/*.sql` | Database apply order and table coverage below |
| `contracts/api/openapi.yaml` | API coverage map below |
| `contracts/schemas/*.json` | Schema registry, extraction validation, review/canonical actions |
| `contracts/events/*.json` | Job/event coverage map below |

## AGENT_START_HERE Milestone Mapping

First milestone, before multimodal extraction:

- Bootstrap first local admin: Phase 0E.
- Durable session: Phase 0E.
- Auth on document/asset routes: Phase 0E and Phase 1D.
- Upload document: Phase 1B.
- Preserve original bytes: Phase 1A.
- Persist fingerprints: Phase 1A/1B.
- Create document and original asset records: Phase 1B.
- Render page thumbnails: Phase 1D.
- Display original document in viewer: Phase 1D.
- Persist job state and surface health: Phase 0F, Phase 1C.
- Show document in inbox: Phase 1C.

Second milestone, before hybrid search:

- PDF to Docling JSON: Phase 3B.
- Persist pages, elements, chunks, raw artifacts: Phase 3B.
- Show extracted text and evidence in UI/debug: Phase 3C and Phase 4E.
- Record extraction runs: Phase 4C.
- Review tasks for failed validations: Phase 4B/4D.
- Idempotent re-run without losing history: Phase 3B, Phase 4C/4D.

Third milestone, before analysis:

- BM25 search: Phase 5A.
- Semantic search: Phase 5B.
- Filtered search: Phase 5C.
- Structured receipt/invoice/EOB views: Phase 4E.
- Manual corrections and audit trails: Phase 4E.
- Related-document navigation: Phase 7.

## OpenAPI Coverage Map

Every OpenAPI path must be assigned to an implementation phase:

| Endpoint | Phase |
| --- | --- |
| `GET/POST/DELETE /api/v1/auth/session` | 0E |
| `POST /api/v1/auth/magic-links` | 0E baseline, 10 hardening |
| `GET/POST /api/v1/documents` | 1B/1C |
| `GET /api/v1/documents/{documentId}` | 1D, expanded in 3/4 |
| `GET /api/v1/assets/{assetId}` | 1D |
| `GET/POST /api/v1/folders` | 2 |
| `GET/POST /api/v1/tags` | 2 |
| `POST /api/v1/documents/{documentId}/organization` | 2 |
| `GET /api/v1/review-tasks` | 4E |
| `POST /api/v1/documents/{documentId}/review-actions` | 4E |
| `GET /api/v1/documents/{documentId}/field-candidates` | 4D/4E |
| `GET/POST /api/v1/documents/{documentId}/canonical-fields` | 4D/4E |
| `POST /api/v1/search` | 5 |
| `GET/POST /api/v1/contacts` | 6 |
| `GET/POST /api/v1/filing-rules` | 6 |
| `GET/POST /api/v1/watched-folders` | 6 |
| `GET/POST /api/v1/relationships` | 7 |
| `POST /api/v1/analysis-notes` | 9 |
| `POST /api/v1/exports` | 10 |
| `GET /api/v1/jobs/{jobId}` | 0F, expanded throughout |
| `GET /api/v1/admin/jobs` | 0F baseline, 10 admin UI |
| `POST /api/v1/admin/jobs/{jobId}/retry` | 0F baseline, 10 admin UI |

## Database Coverage Map

Core database areas and first owning phases:

| Tables / areas | First owning phase |
| --- | --- |
| `households`, `users`, memberships, credentials, sessions, magic links, API tokens | 0E |
| `ingest_batches`, `documents`, `document_assets` | 1A/1B |
| `pipeline_jobs`, service health | 0F |
| `folders`, `folder_acl`, memberships, `tags`, `document_tags`, `saved_searches` | 2 |
| `document_pages`, `document_elements`, `document_tables`, `document_chunks` | 3B |
| `document_extractions`, raw/normalized extraction assets | 4C |
| `field_candidates`, `line_item_candidates` | 4C/4D |
| `canonical_fields`, `canonical_line_items`, `canonical_fact_history` | 4D |
| `review_tasks`, `review_events`, audit events | 4E |
| `embeddings`, BM25/vector indexes, chunk projection columns | 5 |
| `contacts`, aliases, document contacts, filing rules, watched folders | 6 |
| `document_relationships`, deadlines | 7 |
| `analysis_notes` | 9 |
| export assets, audit events, backup/restore operational checks | 10 |
| `evaluation_runs` | 11 |

## Event Contract Coverage Map

| Event schema | First owning phase | Notes |
| --- | --- | --- |
| `ingest_document_job.v1` | 1B | Queue message must stay small; business state lives in DB. |
| `classify_document_job.v1` | 4A | Classification may start heuristic-only. |
| `extract_document_job.v1` | 4C | Targets `document_classification`, `receipt`, `invoice`, `medical_eob`. |
| `embed_document_job.v1` | 5B | Text first; visual/mixed later in Phase 8. |
| `analyze_documents_job.v1` | 9 | Optional, cited, non-canonical analysis. |

## First Build Sequence

The first implementation run should proceed in this exact order unless blocked:

1. Scaffold repo and tooling.
2. Compose Postgres/API/web placeholders.
3. Apply DB baseline.
4. Import contract/schema validation.
5. Implement bootstrap admin/session.
6. Protect route skeletons.
7. Implement job ledger and health.
8. Implement storage abstraction.
9. Implement multipart upload.
10. Implement Inbox UI from Figma.
11. Implement protected asset route and Viewer UI from Figma.
12. Add Playwright workflow and screenshot QA for the first UI slice.

## Phase Artifact Review Rule

Each phase below contains a required artifact list. Before implementing that phase, the agentic coder must read the phase section in this plan and review the required artifact set for that phase. These artifacts are not optional references; they are required context for the implementation work and must be used alongside the phase instructions.

For duplicate Markdown/DOCX pairs in the required artifact lists, review the Markdown file by default when the pair is known to be materially aligned. Review the DOCX only if the user requests layout/fidelity review, the Markdown file appears incomplete, or a material mismatch is suspected.

If the phase plan and a required artifact disagree, apply the source alignment rules above. If the disagreement is material and not resolved by those rules, stop and ask the user.

## Phase 0 - Foundation, Runtime, Contracts, Auth

Objective: build the durable spine before any product workflow depends on it.

Required phase artifacts to review:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/AGENT_START_HERE.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/MANIFEST_v1.3.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/03_Agent_Bootstrap_and_Execution_Order.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/07_Repository_Layout_and_Coding_Standards.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/08_ZFS_Datasets_and_Storage_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/09_Deployment_and_Runtime_Architecture.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/10_Architectural_Decision_Record_Summary.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/15_PGMQ_and_Worker_Strategy.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/16_Auth_ACL_Household_Model.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/19_v1.2_Normalization_and_Source_of_Truth.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/20_Codex_xhigh_Feedback_Resolution.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/001_extensions.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/010_types_and_enums.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/020_core_tables.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/030_constraints_and_triggers.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/050_views_and_functions.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/060_seed_taxonomies.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/api/openapi.yaml
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/ingest_document_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/classify_document_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/extract_document_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/embed_document_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/analyze_documents_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/common_defs.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/zfs/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/zfs/create_datasets.sh
```

### 0A. Repository Scaffold

Create the monorepo layout:

```text
apps/
  web/
  api/
workers/
  ingest/
  previews/
  docling/
  extraction/
  embeddings/
  relationships/
  analysis/
lib/
  config/
  db/
  storage/
  jobs/
  contracts/
  evidence/
  search/
  observability/
  models/
contracts/
database/
infrastructure/
docs/
tests/
```

Tasks:

- Use React + Vite + TypeScript for `apps/web`.
- Use FastAPI + Pydantic for `apps/api`.
- Add shared typed env loading in `lib/config`.
- Add format/lint/test commands.
- Add a task runner or Makefile with bootstrap, test, dev, migrate, and worker commands.
- Copy or reference artifact-pack contracts and SQL without mutating their meaning.

Done:

- Minimal web app boots.
- Minimal API health/version route works.
- Tooling commands are documented.

### 0B. Docker Compose And Runtime

Tasks:

- Compose services: `web`, `api`, `postgres`, worker placeholders, model placeholders.
- Postgres 17 with `pg_search`, `pgvector`, `pgcrypto`, `citext`, `ltree`, `pg_trgm`, `btree_gist`.
- PGMQ bootstrap if compatible with the chosen database image.
- Redis only under explicit fallback profile.
- Model placeholders:
  - `model-qwen` on port `8100`, GPU 0 default.
  - `model-granite` on port `8101`, GPU 0 default for the initial placeholder only; Phase 8.5 supersedes live placement to Blackwell GPU 1.
  - `model-embed` on port `8102`, GPU 1 default for the initial placeholder only; Phase 8.5 supersedes live placement to the RTX 3090 text-embedding node.
  - `worker-analysis` remains optional and must not be required for normal filing/search.
- Bind mounts aligned to:
  - `/srv/structura/postgres`
  - `/srv/structura/objects/canonical`
  - `/srv/structura/objects/derived`
  - `/srv/structura/objects/exports`
  - `/srv/structura/staging`
  - `/srv/structura/cache`
  - `/srv/structura/models`
  - `/srv/structura/logs`

Done:

- `docker compose up` starts healthy services.
- DB persists across restart.
- Extensions can be created.
- Model placeholders expose health or are disabled behind feature flags.

### 0C. Database Baseline

Apply SQL in order:

```text
001_extensions.sql
010_types_and_enums.sql
020_core_tables.sql
025_baseline_identity_acl_candidate_rules.sql
030_constraints_and_triggers.sql
040_indexes_bm25_pgvector.sql
050_views_and_functions.sql
060_seed_taxonomies.sql
```

Tasks:

- Wrap baseline SQL in migration tooling.
- Add schema smoke tests.
- Verify core inserts for households, users, sessions, documents, assets, jobs, folders, tags, candidates, canonical fields.

Done:

- Fresh database can be created from scratch.
- Seed folders and tags exist.
- Baseline schema is queryable.

### 0D. Contract Integration

Tasks:

- Load OpenAPI from `contracts/api/openapi.yaml`.
- Load JSON Schemas from `contracts/schemas`.
- Load event schemas from `contracts/events`.
- Implement a schema registry in `lib/contracts`.
- Generate or hand-map Pydantic models.
- Add validation tests for evidence, upload, session, review actions, field candidates, canonical fields, filing rules, and job events.

Done:

- API request/response models align to OpenAPI.
- Extraction output schemas validate locally.
- Evidence references enforce concrete locators.

### 0E. Auth And Session Foundation

Tasks:

- Bootstrap first household and admin.
- Store bootstrap password in `user_password_credentials` with Argon2id.
- Implement:
  - `POST /api/v1/auth/session`
  - `GET /api/v1/auth/session`
  - `DELETE /api/v1/auth/session`
  - `POST /api/v1/auth/magic-links` stub or bootstrap-capable endpoint.
- Persist `sessions.auth_method`.
- Use `structura_session` HttpOnly cookie.
- Add CSRF protection for browser-mutating routes.
- Add API-token parsing stub.
- Protect document and asset routes by default.

Done:

- First local admin can sign in.
- Anonymous document/asset access is rejected.
- Current session can be resolved from durable DB state.

### 0F. Job And Observability Spine

Tasks:

- Implement `pipeline_jobs` service.
- Add queue adapter: PGMQ preferred, Redis fallback only.
- Implement claim, heartbeat, retry, dead-letter, and status update helpers.
- Add structured logs with correlation IDs.
- Add health endpoints for API and workers.
- Add admin job list/retry API skeleton.
- Ensure job payloads never contain raw document text, raw model output, sensitive extracted fields, or large prompt bodies.

Done:

- Job records are visible and retryable.
- Workers can update state idempotently.
- Logs do not leak raw document content.
- Dead-letter jobs include document link, stage, error class, last error, retry, and dismiss/suppress metadata.

Phase 0 gate:

- Repository, runtime, DB, contracts, auth, and jobs are stable.
- No protected product route is exposed anonymously.

## Phase 1 - Upload, Inbox, Viewer

Objective: create the first trustworthy filing-cabinet workflow.

First working screen: Inbox.

UI implementation must follow `STRUCTURA_UI_FIGMA_QA_PLAN.md`.

Required phase artifacts to review:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/AGENT_START_HERE.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/08_ZFS_Datasets_and_Storage_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/09_Deployment_and_Runtime_Architecture.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/16_Auth_ACL_Household_Model.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/010_types_and_enums.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/020_core_tables.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/050_views_and_functions.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/api/openapi.yaml
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/ingest_document_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/common_defs.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/design-language-dashboard.PNG
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/design-language-v1.3.html
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv
```

### 1A. Object Storage

Tasks:

- Implement content-addressed filesystem storage.
- Use canonical, derived, and export roots.
- Compute SHA-256 during upload.
- Persist `document_assets` rows.
- Keep original writes immutable.
- Add consistency checks between DB and filesystem.

Done:

- Original bytes can be written, retrieved, and hash-verified.
- Duplicate file hashes are detected without silent merge.

### 1B. Upload API And Ingest Kickoff

Tasks:

- Implement multipart `POST /api/v1/documents`.
- Create `documents`, `document_assets`, `ingest_batches`, and `pipeline_jobs`.
- Validate MIME type and size.
- Accept browser upload, API upload, mobile scan, watched-folder, email import, and bulk import source enum values, even if only web upload is implemented first.
- Return `AcceptedJob`.

Done:

- Upload returns document/job identifiers.
- Document appears in inbox without waiting for Docling or extraction.
- Partial failures do not leave dangling rows or orphaned files.

### 1C. Inbox UI

Tasks:

- Implement from Figma frame `17:2`.
- Match Figma shell, sidebar, top bar, table, status chips, metrics, machine health block, pipeline summary, and right evidence inspector.
- Use real API data where available and stable mock rows only where backend stage is not ready.
- Keep Inbox as the default route after sign-in.

Done:

- Inbox displays uploaded documents.
- Selecting a row updates the inspector.
- Processing state is visible.
- Playwright screenshot matches Figma reference within agreed tolerance.

### 1D. Protected Asset Viewer

Tasks:

- Implement `/api/v1/assets/{assetId}` streaming with authorization.
- Generate PDF thumbnails and first-pass page previews before passing Gate A.
- Store preview artifacts as derived assets.
- Link page preview assets to the document/page records where available.
- Implement document detail/viewer from Figma frame `14:434`.
- Show thumbnails, main document page, document facts, trust state, key fields, and actions.

Done:

- User can open a document from Inbox into Viewer.
- Thumbnails render in Inbox/Viewer.
- Original download is routed through authorized API.
- No object-store URI leaks into browser.

Phase 1 gate:

- Upload, inbox, row selection, inspector, and viewer work.
- Originals are immutable and retrievable.
- Thumbnail generation works.
- Playwright validates the workflow and screenshot state.
- Gate A from `AGENT_START_HERE.md` passes.

## Phase 2 - Manual Organization And Filing

Objective: make Structura useful as a manual filing cabinet before AI extraction.

Required phase artifacts to review:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/16_Auth_ACL_Household_Model.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/020_core_tables.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/050_views_and_functions.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/060_seed_taxonomies.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/api/openapi.yaml
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/folder_acl.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/review_action.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/design-language-v1.3.html
```

Tasks:

- Implement folders API and UI.
- Implement tags API and UI.
- Implement document organization update endpoint.
- Allow multiple folder memberships and one primary folder.
- Add notes, title, and document date editing.
- Implement folder/tag portions of the Figma workflow in the third UI priority slice.

Done:

- Documents can be filed manually.
- Folders and tags appear in document lists and detail.
- Audit event is recorded for organization changes where appropriate.

Phase 2 gate:

- Manual filing works even when all model workers are disabled.

## Phase 3 - Preview Worker And Canonical Parse

Objective: create durable structural understanding.

Required phase artifacts to review:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/AGENT_START_HERE.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/08_ZFS_Datasets_and_Storage_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/10_Architectural_Decision_Record_Summary.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/020_core_tables.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/030_constraints_and_triggers.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/api/openapi.yaml
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/ingest_document_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/common_defs.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv
```

### 3A. Preview And Page-Asset Hardening

Tasks:

- Harden thumbnail and page-image generation introduced in Phase 1.
- Generate complete page image sets where Phase 1 only needed first-pass previews.
- Store derived assets under `/srv/structura/objects/derived`.
- Link `document_pages.image_asset_id` and `thumbnail_asset_id`.
- Retry failed preview jobs safely.
- Add cache policy and regeneration behavior.

Done:

- Inbox and Viewer use generated thumbnails/previews.
- Failed preview jobs are visible and retryable.

### 3B. Docling Worker

Tasks:

- Consume `docling_convert` jobs.
- Run Docling conversion for PDFs and image-derived PDFs.
- Persist `docling_json`, optional markdown, optional HTML as derived assets.
- Populate `document_pages`, `document_elements`, `document_tables`, and `document_chunks`.
- Store converter version and metadata.
- Supersede current canonical artifact without deleting history.

Done:

- Every conversion ends with durable artifacts or explicit failure.
- Re-run is idempotent.
- Page/chunk/element rows are inspectable.

### 3C. Canonical Debug Surface

Tasks:

- Add debug panels gated behind an explicit route or flag.
- Show raw Docling artifact, page text, chunks, tables, elements, and job history.
- Do not let debug UI dominate the main workbench.

Done:

- Engineers can inspect parse output before extraction.

Phase 3 gate:

- Canonical parse artifacts and relational rows are durable.
- Parse failures are explicit.
- Gate B from `AGENT_START_HERE.md` passes before extraction work begins.

## Phase 4 - Classification, Extraction, Candidates, Canonicalization

Objective: turn parsed documents into validated, evidence-backed candidate and canonical facts.

Required phase artifacts to review:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/AGENT_START_HERE.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/10_Architectural_Decision_Record_Summary.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/13_Golden_Master_Review_and_Merge_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/14_Canonicalization_Candidate_Authority_Model.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/010_types_and_enums.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/020_core_tables.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/030_constraints_and_triggers.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/050_views_and_functions.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/api/openapi.yaml
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/classify_document_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/extract_document_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/common_defs.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/document_classification.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/receipt.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/invoice.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/medical_eob.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/field_candidate.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/canonical_field.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/review_action.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/design-language-v1.3.html
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv
```

### 4A. Classification

Tasks:

- Implement classification worker using heuristics first, model-assisted later.
- Validate against `document_classification.v1.schema.json`.
- Persist family, subtype, confidence, route profile, evidence, and model trace.
- Allow user reclassification.

Done:

- Documents get useful families and route profiles.
- User corrections preserve history.

### 4B. Extraction Validators

Tasks:

- Implement validators for:
  - `receipt.v1.schema.json`
  - `invoice.v1.schema.json`
  - `medical_eob.v1.schema.json`
- Add arithmetic checks.
- Add missing-required-field checks.
- Add date consistency checks.
- Add evidence adequacy checks.

Done:

- Invalid extraction cannot become accepted canonical fact.
- Validation output is structured.

### 4C. Model Routing And Extraction Workers

Tasks:

- Implement model gateway abstraction.
- Support Docling-only extraction path where sufficient.
- Use Granite for receipts, invoices, EOBs, KVPs, tables, line items.
- Use Qwen for handwriting, ambiguous layouts, OCR rescue, semantic arbitration.
- Persist raw model output assets.
- Persist `document_extractions`.
- Normalize output into `field_candidates` and `line_item_candidates`.

Done:

- Receipt, invoice, and EOB extraction run end-to-end on real samples.
- Raw and normalized outputs are both retained.

### 4D. Canonical Promotion

Tasks:

- Implement authority matrix:
  - Docling: structure and grounding.
  - Granite: tables, KVPs, line items.
  - Qwen: classification, OCR rescue, handwriting, arbitration.
  - Validators: deterministic promotion/rejection.
  - Human: final override.
- Promote candidates only when evidence, schema validation, deterministic validation, confidence, and policy allow.
- Persist `canonical_fields`, `canonical_line_items`, and `canonical_fact_history`.
- Create review tasks for unresolved conflicts.

Done:

- UI reads accepted facts from canonical tables.
- Candidate conflicts are visible in review surfaces.

### 4E. Review Queue And Evidence Inspector

Tasks:

- Implement second UI priority slice from Figma extraction/review surfaces.
- List review tasks.
- Show candidate comparison.
- Show canonical value, evidence, validation state, and history.
- Implement accept, reject, edit, mark reviewed, and re-run extraction.

Done:

- User can resolve uncertain fields.
- Corrections are auditable.
- Evidence jump is one click away.

Phase 4 gate:

- Three target schemas work.
- Evidence is concrete.
- Review tasks are automatic.
- Human corrections do not erase candidates/history.
- Gate C from `AGENT_START_HERE.md` passes before retrieval is treated as product-ready.

## Phase 5 - Lexical, Semantic, Hybrid Search

Objective: make the corpus retrievable by exact, semantic, and filtered queries.

Required phase artifacts to review:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/AGENT_START_HERE.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/10_Architectural_Decision_Record_Summary.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/18_Filter_Aware_Vector_Search_Addendum.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/020_core_tables.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/050_views_and_functions.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/070_query_examples.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/api/openapi.yaml
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/embed_document_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/common_defs.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/design-language-v1.3.html
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv
```

### 5A. BM25 Search

Tasks:

- Use ParadeDB BM25 indexes on documents, chunks, and parties.
- Implement lexical search endpoint.
- Add snippets/highlights where available.
- Add facets and grouping.

Done:

- Exact identifiers, names, claims, and terms are findable.

### 5B. Embeddings

Tasks:

- Implement embedding worker.
- Generate chunk and document embeddings.
- Store model name, version, dimension, modality.
- Use dimension-conscious pgvector indexes.
- Support idempotent re-embedding.

Done:

- Conceptual search works over chunks.

### 5C. Filter-Aware Hybrid Search

Tasks:

- Parse filters for family, folder, tag, date, amount, review status, sensitivity, relationship state.
- Use denormalized chunk projection columns.
- Retrieve BM25 and vector candidates in parallel.
- Use RRF or weighted RRF.
- Apply ACL filters authoritatively before returning results.
- Add optional reranker hook.

Done:

- Hybrid search beats lexical-only and semantic-only on benchmark queries.

### 5D. Search UI

Tasks:

- Implement from Figma frame `14:797`.
- Support global search, advanced filters, result snippets, page references, and result explanations.
- Preserve selected document context when filters change.

Done:

- Search feels like a filing cabinet, not a demo.

Phase 5 gate:

- Lexical, semantic, and hybrid search pass golden queries.
- ACL and filter correctness are tested.
- Gate D from `AGENT_START_HERE.md` passes before analysis is exposed.

## Phase 6 - Contacts, Rules, Watched Folders, Filing Intelligence

Objective: add transparent organization automation.

Required phase artifacts to review:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/13_Golden_Master_Review_and_Merge_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/010_types_and_enums.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/020_core_tables.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/api/openapi.yaml
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/filing_rule.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/folder_acl.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/design-language-v1.3.html
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv
```

Tasks:

- Implement contacts API and UI.
- Link document contacts and aliases.
- Implement watched-folder service with PDF-only ingest first.
- Ignore partial files until stable.
- Avoid recursive ingestion of Structura output directories.
- Implement filing rules with dry-run, explanation, and audit.
- Add rule suggestions in Inbox/Review.
- Add CLI for bulk import, dry run, reprocess, rebuild search, evaluate, backup/restore checks.

Done:

- Contacts improve filing, search, and relationship matching.
- Rules explain why they matched.
- High-stakes documents default to suggested action, not silent finalization.

Phase 6 gate:

- Folder/tag filing workflow and rule suggestions are usable and auditable.

## Phase 7 - Relationships, Timelines, Deadlines

Objective: connect documents into transaction, claim, object, and case histories.

Required phase artifacts to review:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/14_Canonicalization_Candidate_Authority_Model.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/17_Rules_Contacts_and_Watched_Folder_Addendum.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/010_types_and_enums.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/020_core_tables.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/050_views_and_functions.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/api/openapi.yaml
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/review_action.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/design-language-v1.3.html
```

Tasks:

- Implement relationship API and UI.
- Support duplicate, invoice, receipt, EOB, bill, amendment, renewal, attachment, warranty, and payment relationships.
- Implement suggestion worker.
- Implement timeline view.
- Extract and surface deadlines.
- Add smart folders such as needs review, tax relevant, warranties expiring soon, unmatched medical documents.

Done:

- User can traverse from invoice to receipt, bill to EOB, warranty to purchase/service history.

Phase 7 gate:

- Relationships are useful and not merely decorative.

## Phase 8 - Difficult Documents And Visual Retrieval

Objective: improve degraded scans, handwriting, and layout-sensitive retrieval.

Required phase artifacts to review:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/18_Filter_Aware_Vector_Search_Addendum.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/020_core_tables.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/embed_document_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/extract_document_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/common_defs.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv
```

Tasks:

- Detect low-text, handwriting-heavy, visually degraded, and complex-layout pages.
- Add selective visual embeddings.
- Add Qwen-heavy handwriting route.
- Default handwriting outputs to review-required unless quality is high.
- Add visual retrieval endpoint or hybrid inclusion policy.
- Add low-text benchmark cases.

Done:

- Difficult documents are marked with uncertainty and still retrievable.

Phase 8 gate:

- Low-text and handwriting samples have explicit review behavior and benchmark coverage.

## Phase 8.5 - Model And Embedding Services

Objective: replace Phase 8 fixture/fake model behavior with real local model services before Phase 9 analysis is allowed.

Required phase artifact to review:

```text
/Users/brennanconley/vibecode/structura/STRUCTURA_PHASE_8_5_IMPLEMENTATION_PLAN.md
```

Tasks:

- Quarantine deterministic embedding/extraction gateways as fixture-only test adapters.
- Implement live Qwen3-VL-8B service invocation for handwriting, degraded OCR rescue, and visual fallback.
- Implement live Granite 4.0 3B Vision service invocation for table, chart, form, KVP, invoice, bill, receipt, and EOB structure extraction.
- Implement live text embedding service on the RTX 3090 with 1536-dimensional vectors.
- Implement true visual embedding service for page/image bytes with 1024-dimensional vectors.
- Add model profile registry, model health, redacted observability, pinned Compose profiles, and model-backed corpus gates.

Done:

- Qwen and Granite provenance is truthful and tied to actual adapter invocation.
- Visual embeddings are generated from image content, not descriptor-text or byte-hash fixtures.
- Phase 9 analysis has real model-backed retrieval and extraction foundations.

Phase 8.5 gate:

- Qwen3-VL, Granite Vision, text embeddings, and visual embeddings pass deterministic tests plus GPU live model validation.
- Model-backed golden corpus evidence exists for handwriting, structured extraction, text retrieval, visual retrieval, and hybrid retrieval.

## Phase 9 - Analysis Workspace

Objective: add optional cited analysis after filing, extraction, review, and search are strong.

Required phase artifacts to review:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/AGENT_START_HERE.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/10_Architectural_Decision_Record_Summary.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/020_core_tables.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/api/openapi.yaml
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/analyze_documents_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/analysis_note.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/common_defs.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/design-language-v1.3.html
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv
```

Tasks:

- Implement analysis run model.
- Implement `POST /api/v1/analysis-notes`.
- Support summary, explanation, comparison, timeline, obligation scan, tax scan, medical explanation.
- Persist model metadata, prompt version, selected document scope, answer, citations, and recommended actions.
- Implement Figma frame `14:990`.
- Keep analysis separate from canonical facts.

Done:

- Analysis can be disabled without breaking core product behavior.
- Outputs cite documents and pages.
- Analysis never silently mutates accepted extraction data.

Phase 9 gate:

- Citation-backed analysis works and respects sensitivity/ACL policy.
- Gate E from `AGENT_START_HERE.md` passes before analysis is considered releasable.

## Phase 10 - Exports, Security, Backups, Operations

Objective: make Structura safe for daily private archive use.

Required phase artifacts to review:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/08_ZFS_Datasets_and_Storage_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/09_Deployment_and_Runtime_Architecture.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/15_PGMQ_and_Worker_Strategy.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/16_Auth_ACL_Household_Model.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/020_core_tables.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/api/openapi.yaml
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/folder_acl.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/zfs/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/zfs/create_datasets.sh
```

Tasks:

- Implement exports:
  - originals
  - originals plus JSON
  - originals plus CSV
  - review report
- Include export manifest and provenance.
- Audit export events.
- Add passkey/WebAuthn hardening.
- Add API token lifecycle UI.
- Add folder ACL management.
- Add session timeout, rotation, revoke-all.
- Implement backup procedures for DB, object storage, config, repo.
- Implement restore rehearsal.
- Add admin jobs, service health, storage usage, model health, extraction failure stats.

Done:

- Backup and restore are tested.
- Sensitive routes remain protected.
- Admin can retry dead-letter jobs.

Phase 10 gate:

- Restore has been rehearsed.
- Auth hardening matches intended exposure.
- Operational visibility is enough for self-hosting.

## Phase 11 - Golden Corpus, Regression, Release Candidate

Objective: measure quality and prevent quiet regressions.

Required phase artifacts to review:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/AGENT_START_HERE.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.docx
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/001_extensions.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/010_types_and_enums.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/020_core_tables.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/030_constraints_and_triggers.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/050_views_and_functions.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/060_seed_taxonomies.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/database/070_query_examples.sql
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/api/openapi.yaml
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/ingest_document_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/classify_document_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/extract_document_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/embed_document_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/events/analyze_documents_job.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/analysis_note.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/canonical_field.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/common_defs.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/document_classification.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/field_candidate.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/filing_rule.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/folder_acl.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/invoice.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/medical_eob.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/receipt.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/contracts/schemas/review_action.v1.schema.json
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/zfs/README.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv
```

Tasks:

- Assemble secured local golden corpus:
  - receipts
  - invoices
  - EOBs and medical bills
  - warranties
  - legal notices
  - handwritten notes
  - long reference PDFs
- Store expected classifications, key fields, review expectations, and search queries.
- Implement extraction scoring.
- Implement search benchmark scoring.
- Implement Playwright UI smoke tests.
- Implement migration-from-scratch tests.
- Run restore tests.

Done:

- No critical data-integrity bugs.
- No broken provenance links on tested samples.
- Hybrid search quality is measured.
- Known issues are documented.

Release candidate gate:

- Migrations pass from scratch.
- Golden search tests pass.
- Extraction metrics meet approved thresholds.
- Restore rehearsal passes.
- Playwright workflow tests pass.

## Testing Matrix By Phase

| Phase | Required verification |
| --- | --- |
| 0 | Unit tests for config/contracts; DB migration-from-scratch; auth/session smoke; job ledger smoke |
| 1 | Upload integration test; object hash/retrieval test; protected asset test; Playwright Inbox/Viewer workflow and screenshots |
| 2 | Folder/tag CRUD tests; document organization integration test; audit event check |
| 3 | Preview worker integration; Docling artifact persistence; page/element/chunk row count checks; idempotent re-run test |
| 4 | Schema validation fixtures; arithmetic checks; evidence adequacy tests; review action integration; candidate/canonical promotion tests |
| 5 | BM25 query tests; embedding storage tests; filter-aware vector tests; hybrid RRF benchmark; ACL negative tests |
| 6 | Watched-folder dry run; filing-rule dry run/apply tests; contact alias/dedupe tests |
| 7 | Relationship creation/suggestion tests; timeline ordering tests; deadline extraction display tests |
| 8 | Low-text/handwriting routing tests; visual embedding storage tests; uncertainty/review-required tests |
| 9 | Analysis citation tests; sensitivity/ACL tests; non-mutation of canonical facts |
| 10 | Export manifest tests; backup/restore rehearsal; session/token hardening tests; admin retry tests |
| 11 | Golden corpus extraction/search regression; end-to-end Playwright smoke; release checklist |

## Open Technical Decisions To Resolve At The Owning Phase

These are known flex points from the artifact pack and should not be accidentally decided by implementation drift:

| Decision | Resolve by | Notes |
| --- | --- | --- |
| Exact Postgres/ParadeDB/PGMQ image and extension packaging | Phase 0B | If PGMQ blocks progress, document Redis fallback profile while retaining `pipeline_jobs`. |
| SQLAlchemy vs SQLModel vs raw SQL split | Phase 0A/0C | Search-heavy flows may use raw SQL; route handlers should stay orchestration-only. |
| PDF rendering/thumbnail library | Phase 1D/3A | Must support protected asset flow and stable previews. |
| Exact embedding model and dimension | Phase 5B | Artifact default expects dimension-conscious pgvector indexes, commonly 1536 text and 1024 visual unless changed. |
| Visual embeddings default-on vs selective | Phase 8 | Artifact risk register leaves this open. Use selective unless the user decides otherwise. |
| Redaction in v1 exports | Phase 10 | Artifact risk register leaves redaction as an open v1 question. |
| Analysis notes editable vs immutable | Phase 9 | Artifact risk register leaves this open. Default to immutable generated artifact plus user-created follow-up notes unless decided otherwise. |
| Email ingestion timing | Phase 6 or later | Upload and watched-folder are enough for first usable release unless user prioritizes email. |
| Duplicate detection aggressiveness beyond exact hash | Phase 7/11 | Start exact hash; structural similarity later with review required. |

## Continuous Workstreams

- Keep prompts versioned and checked in.
- Store model name, model version, prompt version, schema version for every run.
- Keep JSON Schemas, OpenAPI models, DB tables, and UI read models aligned.
- Expand golden corpus as soon as real samples exist.
- Update ADRs when implementation diverges from the artifact baseline.
- Do not cut provenance, validation, review state, or original-asset integrity to save time.

## Future UI Question Rule

If the Figma file, dev redlines, interaction specs, edge-state pages, or this plan do not resolve a UI/UX decision, stop and ask the user before implementing that UI behavior.
