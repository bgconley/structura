# Structura Agent Guidance

## Planning Source Of Truth

Use `STRUCTURA_IMPLEMENTATION_PLAN.md` as the phase map and sequencing source of truth.

The root implementation plan is not comprehensive by itself. Before implementing any phase or subphase, pull in the associated non-archive artifacts listed by the root plan and any directly related artifact-pack docs, contracts, database SQL, and infrastructure files.

Do not inspect or rely on anything under `archive/`.

## File Review Handling

When an artifact exists in both Markdown and DOCX form, read the Markdown file by default. Only inspect the DOCX version when the user explicitly asks for DOCX/layout fidelity or when the Markdown artifact is missing or appears incomplete.

For large files, avoid broad combined `cat` reads that may be truncated by terminal-output limits. Verify file length with `wc -l`, then read the file in bounded, non-overlapping chunks such as `sed -n '1,250p'` so full coverage is explicit.

## Architecture Stewardship

Treat maintainability as part of the requested work. Working code is not sufficient if it leaves the codebase more coupled, ambiguous, or difficult to test.

Before editing code, inspect the target files and decide whether the change belongs there. If a file is accumulating unrelated responsibilities, pause and refactor or propose a refactor before adding more logic.

Prefer these boundaries:

1. API routes/controllers stay thin: request parsing, auth/dependency wiring, and response construction.
2. Schemas/DTOs own input/output shapes and validation.
3. Services own business rules, orchestration, workflow behavior, and application-level decisions.
4. Repositories/DAOs own persistence, database queries, transactions, and storage details.
5. Domain modules own core business concepts and infrastructure-independent rules.
6. Adapters isolate external APIs, SDKs, filesystems, queues, model providers, and vendor behavior.
7. Utilities stay small, generic, and genuinely reusable; do not dump domain logic into vague utility modules.
8. Tests should mirror the structure of the code they validate.

Actively avoid god files, god classes, kitchen-sink utilities, circular imports, business logic hidden in route handlers or UI components, random database queries spread through the codebase, broad catch-all exception handling, vague `manager`/`processor`/`helper` modules, and boolean-flag explosions.

Use these size heuristics as warning signals, not hard limits:

1. If a file is approaching 300-500 lines and is still growing, inspect its responsibilities.
2. If a file exceeds 500 lines, treat it as a refactor candidate unless it is generated code, declarative schema, migration SQL, fixture data, or intentionally large.
3. If a file exceeds 800 lines, do not add more logic without refactoring or explicitly justifying why the file should remain large.
4. If a function exceeds roughly 50-75 lines, inspect whether it contains phases that should be extracted.
5. If a class exceeds roughly 200-300 lines, inspect whether it owns too many responsibilities.

When refactoring, preserve behavior first. Prefer small, incremental extractions with clear names and clean dependency direction. Create a new module only when the extracted code has a clear responsibility, can be understood independently, reduces future change risk, and makes tests easier to write. Do not create abstractions only to satisfy file-count or line-count aesthetics.

Naming should describe ownership. Avoid names like `misc.py`, `helpers.py`, `common.py`, `stuff.py`, `manager.py`, `processor.py`, or `logic.py` unless the surrounding package makes the responsibility precise. Prefer domain names such as `document_ingestion.py`, `organization_repository.py`, `folder_policy.py`, `auth_policy.py`, `import_manifest.py`, or `export_bundle.py`.

Layering direction matters: outer layers may depend on inner layers, but domain/business logic should not depend on web frameworks, CLI frameworks, database clients, HTTP clients, cloud SDKs, or UI frameworks. Route/UI code may call services; services may call repositories and adapters; repositories may know about the database.

Before declaring work complete, inspect every touched file and answer:

1. Does this file still have one clear responsibility?
2. Did the change land in the correct architectural layer?
3. Did the change introduce dependency direction problems or circular imports?
4. Did the change make future testing easier rather than harder?
5. Did the change avoid creating or worsening a god module?
6. Was behavior preserved, and were relevant checks run?

If any answer is concerning, fix it before calling the work complete.

## Conflict Resolution

When artifacts differ:

1. Use `STRUCTURA_IMPLEMENTATION_PLAN.md` for phase order, stop points, and gate sequencing.
2. Use v1.3 normalization and ADR artifacts, `contracts/`, `database/`, and `infrastructure/` for technical truth and acceptance detail.
3. Preserve artifact-pack semantics unless a runtime compatibility issue is proven and documented.
4. Document any intentional divergence in an ADR or equivalent project note.

## Phase 0 Orientation

The current root plan breaks Phase 0 into:

1. `0A` Repository Scaffold
2. `0B` Docker Compose And Runtime
3. `0C` Database Baseline
4. `0D` Contract Integration
5. `0E` Auth And Session Foundation
6. `0F` Job And Observability Spine

Older artifact-pack docs may group the same work differently. Treat the root plan as the active sequencing layer and the artifact pack as required implementation depth.

## Current Baseline And Next Phase

As of 2026-04-27, the repo is implemented through Phase 7 on `master`; local, `origin/master`, and the GPU checkout at `/tank/repos/structura` must stay synced before any milestone validation. Phase 8 is the next implementation phase and must start from `STRUCTURA_PHASE_8_IMPLEMENTATION_PLAN.md` plus its Fresh Context artifacts.

Phase 4 implementation code landed in commit `d04a762` (`Implement Phase 4 extraction review`). It adds the extraction/review foundation; before calling the phase complete, current HEAD must be pushed, pulled on the GPU node, migrated through `068_phase4_extraction_review.sql`, rebuilt with the extraction profile, and validated on the GPU node.

Phase 2 includes manual organization only: manual folders, smart-folder records, tags, document title/date/filing-notes edits, multi-folder membership, primary folder selection, folder filtering, list/detail propagation, audit coverage, and usable Inbox/Viewer filing surfaces. Do not treat dynamic smart-folder execution, filing-rule automation, watched-folder ingestion, model-based filing suggestions, extraction review workflows, Docling parsing, or search ranking as Phase 2 scope; those belong to later phases unless the user explicitly changes scope.

The Phase 2 hardening pass closed these previously confirmed gaps: cross-household job/admin visibility, dead-letter retry jobs that could not be claimed, buffered web proxy upload/download behavior, placeholder preview-worker execution, and incomplete folder/tag filing screenshot artifacts. Preserve those regression tests and authz/retry/proxy/worker seams when starting Phase 3.

Phase 3 adds the canonical parse foundation only: queued Docling conversion, immutable derived parse artifacts, relational `document_pages`, `document_elements`, `document_tables`, and `document_chunks`, page preview asset refresh, protected admin parse-debug API, and Viewer parse-debug UI. Do not implement Phase 4 classification, extraction, model-gateway, candidate normalization, canonical promotion, review queue, or evidence-review workflow while finishing Phase 3 seams.

Docling and its Torch/OpenCV dependency stack must stay isolated to the dedicated `worker-docling` image. Do not add Docling/Torch to shared API/previews requirements or the host GPU venv as a runtime dependency. If the API/previews image cannot import Docling, that is intentional; only `worker-docling` owns the real converter.

The Phase 3 Docling worker configures the PDF pipeline explicitly. OCR is disabled by default for deterministic digital-PDF conversion, table structure remains enabled, and Hugging Face/XDG/RapidOCR caches must stay under `/srv/structura/cache` through Compose environment or equivalent runtime configuration. Do not let OCR/model downloads write into Python site-packages.

Phase 4 adds the extraction/review foundation only: classification over canonical Docling parse text, deterministic Docling-text extraction gateway, receipt/invoice/EOB validators, field and line-item candidates, canonical fact promotion, review task/action APIs, and Review Queue UI.

Phase 5 adds corpus retrieval only: Phase 4 fact/chunk projection refresh, BM25 lexical search with fallback, deterministic local text embeddings, `worker-embeddings`, semantic retrieval, hybrid RRF ranking, ACL-aware filters/facets, saved searches, smart-folder execution through planner-parity saved-query parsing, and Corpus Search UI. Do not implement Phase 6 contacts, contact aliases, watched-folder intake, filing-rule automation, rule suggestions, or contact/rule management while finishing Phase 5 validation.

Phase 6 adds transparent organization automation only: contacts, aliases, document-contact links, duplicate merge suggestions, watched-folder PDF intake, filing rules, dry-run explanations, reviewable filing suggestions with accept/reject/defer actions, rule application through the shared rule-action/manual organization path, import/maintenance CLI commands, and the Automation Workbench UI. Do not implement Phase 7 relationship graphs, relationship suggestion workers, timelines, deadlines, missing companion document suggestions, or relationship-aware smart views while finishing Phase 6 validation.

Phase 7 adds relationship intelligence only: document relationship persistence, manual relationship creation/accept/reject, deterministic relationship suggestions, a real `worker-relationships`, relationship review actions, related-document Viewer panels, entity/document timelines, deadline extraction from accepted canonical date fields, relationship/deadline-aware search filters/facets/smart views, and the Relationships/Timelines UI. Do not implement Phase 8 visual retrieval, handwriting/Qwen routes, visual embeddings, low-text image fallback, mixed text/visual ranking, or difficult-document visual QA while finishing Phase 7 validation.

Phase 6 remediation landed in commits `45193ba` (`Harden Phase 6 automation gaps`) and `7111b83` (`Tighten Phase 6 live selector`). It closed the Phase 6 audit gaps by applying every declared filing-rule action (`add_folder`, `set_primary_folder`, `add_tag`, `set_sensitivity`, `set_document_type`, `create_review_task`), making direct rule application and suggestion acceptance transactionally atomic with filing-rule run/audit persistence, enforcing watched-folder allowed roots through `STRUCTURA_WATCHED_FOLDER_ROOT`, rejecting symlinked watched-file candidates, aligning later-phase placeholder OpenAPI responses to runtime `501`, expanding the Automation Workbench UI, adding Phase 6 to the GPU live smoke workflow, and implementing `bulk-import --execute` through the authenticated upload API.

Phase 6 was canonically validated on the GPU node at commit `7111b83`: `api`, `web`, and `worker-watched-folders` were rebuilt/restarted; `ruff`, format check, contract validation, `pytest` with live Postgres (`90 passed`), `make sast`, `pyright`, `mypy`, pinned `node:20-alpine` web lint/build, Compose config/health, and the full live Playwright suite for phases 1-6 against `http://10.25.0.50:13000` all passed. A Mac host `npm` build failure after Linux-container dependency writes is not valid milestone evidence; keep web verification in pinned container/app images.

Phase 7 implementation landed in commits `13ce60d`, `6641368`, `479cb78`, and `eebdb3d`. It added `database/073_phase7_relationships.sql`, `apps/api/structura_api/routes_relationships.py`, cohesive `lib/relationships/*` repositories/services/suggestions/jobs, `workers/relationships/worker.py`, relationship/deadline/timeline contract models and OpenAPI paths, relationship/deadline search filters/facets, related-document Viewer UI, Relationship Workspace UI, Phase 7 mocked/live Playwright specs, and `docs/ui-reference/figma/relationships-timelines/`.

Phase 7 hardening closed the validation gaps found during GPU testing: deadline refresh now joins `field_candidates` for confidence instead of reading a non-existent `canonical_fields.confidence`, relationship persistence was split into `relationship_repository.py`, `deadline_repository.py`, and `timeline_repository.py` instead of a 700-line repository god module, live Playwright selectors are scoped for shared-GPU-DB duplicate labels, and the Phase 4 rerun integration test waits for terminal job success when the live Compose extraction worker races the in-process drain helper.

Phase 7 was canonically validated on the GPU node at commit `eebdb3d`: migration `073_phase7_relationships.sql` applied; `api`, `web`, `worker-extraction`, `worker-embeddings`, `worker-watched-folders`, and `worker-relationships` rebuilt/restarted with the active profiles; `ruff`, format check, contract validation, `pytest` with live Postgres (`97 passed`), `make sast`, `pyright`, `mypy`, pinned `node:20-alpine` web lint/build, Compose config/health, and the full live Playwright suite for phases 1-7 against `http://10.25.0.50:13000` all passed.

Phase 5 hardening landed in commit `81abea2` (`Harden Phase 5 search and ingest gaps`). It closed the Phase 5 audit gaps by moving smart-folder saved-query semantics into `lib/search/saved_query.py` and `lib/documents/list_repository.py`, expanding `SearchFilters`/OpenAPI/UI support for review-status, folder, tag, sensitivity, date, and amount filters, replacing the placeholder ingest container with `workers/ingest/worker.py`, adding `database/071_phase5_search_guardrails.sql`, aligning Phase 6 placeholder POST contracts to runtime `501`, adding CI workflows, and adding a small search benchmark harness.

The Phase 5 hardening pass also preserved architecture boundaries: document list SQL now lives in `lib/documents/list_repository.py`, document summary row mapping lives in `lib/documents/summary_mapping.py`, search request/filter UI state lives in `apps/web/src/components/SearchFilterPanel.tsx`, and `lib/documents/read_model.py` returned to a focused document-detail read model. Do not undo these extractions by moving list filtering, saved-query parsing, or UI filter-state construction back into oversized read-model, route, or component files.

Phase 5 was canonically validated on the GPU node at commit `81abea2`: migration `071_phase5_search_guardrails.sql` applied; `api`, `web`, and `worker-ingest` rebuilt/restarted; `ruff`, format check, contract validation, `pyright`, `mypy`, `pytest` with live Postgres (`73 passed`), `make sast`, pinned `node:20-alpine` web lint/build, Compose config/health, and the full live Playwright suite for phases 1-5 against `http://10.25.0.50:13000` all passed. Runtime probes confirmed unsupported smart-query keys no longer match, authenticated Phase 6 placeholder POST `/api/v1/contacts` returns `501`, and the ingest queue had no queued/running backlog after the real ingest worker started.

Historical Phase 4-to-Phase 5 seams that Phase 5 consumed:

1. Canonical accepted facts are stored in `canonical_fields`/`canonical_line_items` and exposed on document detail for search indexing and answer grounding.
2. Phase 4 refreshes `document_chunks` lexical projection through `refresh_document_chunk_projection(document_id)`, appending accepted canonical facts into `bm25_text` without implementing Phase 5 retrieval.
3. Document rollups now populate `counterparty_display`, `document_date`, and Phase 4 total amounts from accepted canonical fields, leaving filter/facet inputs ready for Phase 5.
4. Extraction artifacts are immutable derived assets, while current raw/normalized extraction assets are superseded before reruns to preserve the one-current-asset invariant.
5. Review actions audit human acceptance/correction/rerun intent through `review_events` and `canonical_fact_history`, so Phase 5 can distinguish candidate, auto-accepted, user-confirmed, and user-corrected facts.
6. `worker-extraction` processes `classify` and `extract` jobs behind the Compose `extraction` profile; Phase 5 should add embedding/search workers as separate queues/modules, not fold them into extraction.
7. Authorization remains centralized through `document_is_readable(document_id, household_id, user_id, household_role)` and must be reused for Phase 5 search result visibility and evidence reads.
8. UI reference artifacts now include `docs/ui-reference/figma/review-extraction/` and the deterministic Linux snapshot `tests/e2e/phase4.spec.ts-snapshots/phase4-review-queue-chromium-linux.png`.

Preserve the Phase 5 search architecture guardrail: do not append search, embedding, or ranking logic to document routes, review routes, or extraction modules. Follow the architecture stewardship rules: keep cohesive search/retrieval modules and workers; keep route handlers thin; put SQL in repositories or schema functions; and keep model-provider/vendor behavior behind adapters.

Phase 6 integration seams are ready after Phase 5:

1. Search visibility is enforced through `document_is_readable(document_id, household_id, user_id, household_role)` in `lib/search/repository.py`; Phase 6 contacts/rules/search conditions must not bypass this predicate.
2. Search projection refresh is exposed through `lib/search/projection.py::refresh_projection_and_enqueue_embedding`; Phase 6 filing, contact-link, and rule-application mutations should call this seam after changing searchable document metadata.
3. Embedding jobs are isolated on the `embeddings` queue and processed by `workers/embeddings/worker.py`; do not fold Phase 6 filing-rule or contact workers into the embedding worker.
4. Saved searches are household-scoped through `/api/v1/saved-searches`; smart folders parse saved-query JSON through `lib/search/saved_query.py` and resolve document lists through the same `document_filter_sql` planner predicates as `/api/v1/search`. The database `document_matches_saved_query` function remains as a guardrail and compatibility helper, but it must not become a divergent second planner.
5. Search API/UI modules live under `apps/api/structura_api/routes_search.py`, `lib/search/`, `lib/documents/list_repository.py`, `apps/web/src/components/SearchResults.tsx`, and `apps/web/src/components/SearchFilterPanel.tsx`; Phase 6 should add separate organization automation modules instead of extending these with contacts/rule orchestration.
6. Relationship-aware chips in the Phase 5 UI are a future seam only; Phase 7 relationship graph retrieval is not implemented by Phase 5.
7. Phase 6 placeholder POST endpoints for contacts, filing rules, and watched folders intentionally advertise and return `501` until Phase 6 implements them. When implementing Phase 6, update runtime behavior, OpenAPI request/response contracts, and parity tests in one change set.

Historical Phase 6-to-Phase 7 seams that Phase 7 consumed:

1. Contacts and aliases live in `contacts`/`contact_aliases`; document-contact links live in `document_contacts`, are exposed through `/api/v1/documents/{documentId}/contacts`, and refresh search projection through `lib/search/projection.py`.
2. Filing-rule suggestions live in `filing_rule_runs` with `decision_status` values `pending`, `accepted`, `rejected`, and `deferred`; Phase 7 relationship suggestions should use separate relationship tables/workers rather than overloading filing-rule runs.
3. Rule application now flows through `lib/automation/action_application.py` and `lib/organization/document_organization.py` with a caller-supplied cursor, so folder/tag/metadata/review-task mutations and `filing_rule_runs` updates commit or roll back together. Do not bypass this seam or reintroduce independently committing manual filing inside automation apply/accept flows.
4. Watched-folder intake is isolated in `workers/watched_folders/worker.py`, imports only stable PDF files through `lib/documents/ingestion.py`, validates watched roots against `STRUCTURA_WATCHED_FOLDER_ROOT` (default `/srv/structura/imports`), and rejects symlinked file candidates. Phase 7 must not fold relationship discovery into this intake scanner or expand filesystem trust boundaries without an explicit policy change.
5. Operator maintenance enqueues normal jobs through `lib/documents/maintenance.py`; reprocess and search rebuild commands should enqueue queue work, not mutate parse/search tables directly.
6. Deferred relationship, analysis, and export POST endpoints intentionally advertise and return `501` until their owning phases implement them. Phase 7 relationship implementation must update runtime routes, OpenAPI success contracts, and parity tests in one change set.
7. `worker-relationships` remains a future placeholder for Phase 7. Relationship graph/timeline/deadline work should add cohesive relationship services/repositories/workers and keep automation/search/document routes thin.
8. Phase 6 automation UI evidence lives under `docs/ui-reference/figma/automation/` with the deterministic Linux snapshot `tests/e2e/phase6.spec.ts-snapshots/phase6-automation-workbench-chromium-linux.png`.
9. The Automation Workbench is intentionally split into focused components (`AutomationContactsPanel`, `AutomationRulesPanel`, `AutomationSuggestionsPanel`, `AutomationWatchedPanel`, `AutomationImportsPanel`, `AutomationTabs`, and `automationFormatting`). Do not collapse these back into a god component while adding Phase 7 relationship surfaces.

Phase 8 integration seams are ready after Phase 7:

1. Relationship visibility requires both documents to pass `document_is_readable`; preserve this ACL rule for any Phase 8 evidence, visual preview, or mixed-retrieval relationship context.
2. Text retrieval remains the default search path. Phase 8 visual embeddings and mixed ranking must be opt-in through dedicated visual modules/workers and must not replace the Phase 5 text embedding pipeline or Phase 7 relationship filters.
3. Relationship/deadline smart views are planner-backed through `SearchFilters`, `lib/search/repository.py`, and `lib/search/saved_query.py`; Phase 8 should add visual/low-text filters through the same canonical planner path rather than creating divergent saved-query semantics.
4. Relationship suggestions and manual decisions are reviewable through relationship-specific persistence and `accept_relationship`/`reject_relationship` review actions. Phase 8 uncertainty/handwriting review tasks should add their own typed actions instead of overloading filing-rule runs or relationship status.
5. Deadlines are derived from accepted canonical date fields and selected candidate confidence; Phase 8 extraction improvements should continue to promote facts through canonical fields before deadlines/search/timelines consume them.
6. `worker-relationships` is now a real queue consumer behind the `relationships` Compose profile. Phase 8 visual/handwriting workers should be separate queues/profiles and must not be folded into relationships, extraction, or embeddings workers.
7. Phase 7 UI reference artifacts live under `docs/ui-reference/figma/relationships-timelines/` with deterministic Playwright snapshots. Any Phase 8 UI addition needs its own reference/snapshot set and must keep live specs scoped for shared GPU database state.

## Figma And UI Reference Baseline

Strict UI evidence now lives under `docs/ui-reference/figma/`:

```text
docs/ui-reference/figma/inbox/
docs/ui-reference/figma/viewer/
docs/ui-reference/figma/folder-tag-filing/
docs/ui-reference/figma/parse-debug/
docs/ui-reference/figma/review-extraction/
docs/ui-reference/figma/search/
docs/ui-reference/figma/automation/
docs/ui-reference/figma/relationships-timelines/
```

Inbox uses Figma frame `17:2`; Viewer uses `14:434`. Phase 2 folder/tag filing uses a composite Figma source set rather than one dedicated final filing frame: primary frame `17:2`, Viewer propagation frame `14:434`, future review-workspace reference `14:611`, and handoff frames `35:7`, `35:12`, and `35:17`. The older filing-rules/watched-folders mockups are automation scope and are not the Phase 2 manual filing baseline.

The folder/tag filing capture pass added `figma-context.json`, Figma screenshots, handoff screenshots, an extraction-workspace reference screenshot, and the deterministic Playwright comparison screenshot. Keep these artifacts synchronized with any future UI changes and run the Playwright screenshot assertions rather than writing ad hoc screenshots directly into committed reference paths.

The parse-debug reference set documents the Phase 3 Viewer diagnostic extension and includes `figma-context.json`, `comparison-notes.md`, `playwright-screenshot.png`, and the Linux Playwright snapshot `tests/e2e/phase3.spec.ts-snapshots/phase3-parse-debug-chromium-linux.png`. The review-extraction reference set documents the Phase 4 Review Queue and includes `figma-context.json`, `comparison-notes.md`, `figma-screenshot.png`, `playwright-screenshot.png`, and the Linux Playwright snapshot `tests/e2e/phase4.spec.ts-snapshots/phase4-review-queue-chromium-linux.png`. The search reference set documents the Phase 5 Corpus Search surface and includes `figma-context.json`, `comparison-notes.md`, `figma-screenshot.png`, `playwright-screenshot.png`, and the Linux Playwright snapshot `tests/e2e/phase5.spec.ts-snapshots/phase5-corpus-search-chromium-linux.png`. The automation reference set documents the Phase 6 Automation Workbench and includes `figma-context.json`, `comparison-notes.md`, `playwright-screenshot.png`, and the Linux Playwright snapshot `tests/e2e/phase6.spec.ts-snapshots/phase6-automation-workbench-chromium-linux.png`. The relationships-timelines reference set documents the Phase 7 related-document and timeline surface and includes `figma-context.json`, `comparison-notes.md`, `playwright-screenshot.png`, and the Linux Playwright snapshot `tests/e2e/phase7.spec.ts-snapshots/phase7-relationships-timeline-chromium-linux.png`.

## GPU Node Runtime And Test Policy

Do not treat Mac-only validation as phase or major-milestone completion evidence. Local Mac runs are allowed only as quick preflight checks. For live, integration, runtime, Docker, model, or milestone-completion validation, commit locally, push to GitHub, SSH to the GPU node, pull the pushed commit there, then build and test on the GPU node.

GPU node connection and checkout settings from `STRUCTURA_PLAN_INDEX.md`:

```text
Host: 10.25.0.50
SSH user: bgconley
SSH key: /Users/brennanconley/vibecode/infx/ubuntu24_ed25519
Remote git URL: https://github.com/bgconley/structura.git
GPU node repo path: /tank/repos/structura
GPU node virtualenv root: /tank/venvs
```

Before creating any GPU-node directory or ZFS dataset, inspect the current node state with `zfs list`, `zpool list`, `findmnt`, and `ls`. Do not assume paths are missing. As of 2026-04-25, `/tank/repos` already exists as the `tank/repos` ZFS dataset and `/tank/repos/structura` already exists as a checkout directory. Application virtualenvs on the GPU node must be created under `/tank/venvs`, not inside the repository and not under `/tank/repos`; as of 2026-04-25, `/tank/venvs` exists as a directory on the root ext4 filesystem, not as a dedicated ZFS dataset.

Persistent runtime state follows the ZFS plan in `pro-merged-master-v1.2/docs/08_ZFS_Datasets_and_Storage_Plan.md` and `pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv`. The recommended pool example is `tank/structura`, mounted at `/srv/structura`; `POOL` in the matrix is a placeholder. Runtime root for Compose bind mounts is `${STRUCTURA_RUNTIME_ROOT:-/srv/structura}`.

Key runtime paths:

```text
Runtime root: /srv/structura
Postgres data: /srv/structura/postgres
Redis fallback data: /srv/structura/redis
Canonical objects: /srv/structura/objects/canonical
Derived objects: /srv/structura/objects/derived
Exports: /srv/structura/objects/exports
Model storage: /srv/structura/models
Staging: /srv/structura/staging
Cache: /srv/structura/cache
Runtime config: /srv/structura/config
Logs: /srv/structura/logs
Backups: /srv/structura/backups
Observability: /srv/structura/observability
Temporary utilities scratch: /srv/structura/tmp
```

Docker bind mounts are the `/srv/structura` paths declared in `compose.yaml` and `pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv`: Postgres uses `/srv/structura/postgres`; API uses `config/api`, `objects/canonical`, `objects/derived`, `objects/exports`, `cache`, and `logs/api`; web uses `config/web` and `cache`; ingest uses `staging`, `objects/canonical`, and `logs/workers`; previews uses `staging`, `objects/derived`, `cache`, and `logs/workers`; Docling uses `staging`, `objects/canonical:ro`, `objects/derived`, `cache`, and `logs/workers`; extraction, embeddings, relationships, and analysis use `objects/derived` and `logs/workers`; model services use `models` and `logs/models`; Redis fallback uses `redis`.

The artifacts do not define a Docker daemon image-store/data-root path. Do not invent or change Docker image storage without a new explicit decision or ADR; use the GPU node's existing Docker configuration until that decision is made.

Do not install or rely on host `node` or `npm` on the GPU node for Structura verification. The GPU host should provide orchestration capabilities such as `ssh`, `git`, `docker`, `docker compose`, ZFS tools, and Python venv tooling for Python-side gates. Web lint/build and browser E2E gates must run through pinned container images or app images so Node/npm versions stay tied to the runtime/test image contract. Current pinned surfaces are `node:20-alpine` for the web app image and `mcr.microsoft.com/playwright:v1.59.1-noble` for browser E2E.

Playwright milestone validation must target the GPU-hosted web service, not a Mac-hosted Vite server. The Mac can act as the browser/controller, but the app under test must be served from the GPU node on the LAN. Current live UI target is `http://10.25.0.50:13000` with `STRUCTURA_E2E_LIVE=1`; the GPU Compose `.env` should expose only web externally via `STRUCTURA_WEB_BIND_HOST=0.0.0.0` and `STRUCTURA_WEB_PORT=13000`, while keeping API and Postgres bound to `127.0.0.1`. The canonical live browser milestone suite must include every implemented phase live spec: `tests/e2e/phase1-live.spec.ts`, `tests/e2e/phase2-live.spec.ts`, `tests/e2e/phase3-live.spec.ts`, `tests/e2e/phase4-live.spec.ts`, `tests/e2e/phase5-live.spec.ts`, `tests/e2e/phase6-live.spec.ts`, and `tests/e2e/phase7-live.spec.ts`.

Do not substitute backend integration tests or mocked Playwright screenshot tests for a phase's live browser smoke when that phase has a user-visible UI/runtime workflow. Phase 3 specifically requires `tests/e2e/phase3-live.spec.ts`, which uploads a generated valid PDF through the GPU-hosted web UI, waits for the live Docling worker to persist parse artifacts, and verifies the Parse Debug panel in the Viewer. The deterministic PDF helper lives at `tests/e2e/support/pdf.ts`. When a new phase adds a browser-visible workflow, add a corresponding `phaseN-live.spec.ts` or explicitly document why no live browser spec is applicable before calling the phase complete.

Live Playwright specs run against a shared GPU-hosted database that may contain artifacts from previous phase runs. Use unique markers and scoped locators for target rows/cards/buttons rather than page-wide text or role selectors when duplicate labels are possible. Preserve earlier-phase UI assertions as later phases add downstream jobs: the Phase 3 Parse Debug panel must continue to surface `docling_convert` status even after Phase 4/5 classify/extract/embed jobs exist. Search snippets returned to clients should be plain text; do not expose BM25/ParadeDB highlight markup or assert exact hyphenated query strings after search highlighting/tokenization.

Observed GPU-node ZFS state on 2026-04-25:

```text
Pool: tank, ONLINE, size 3.62T, allocated 376G, free 3.26T
Existing relevant dataset: tank/repos mounted at /tank/repos
Existing repo checkout: /tank/repos/structura
Existing venv directory: /tank/venvs, currently on root ext4 rather than a dedicated ZFS dataset
Existing Docker root: /var/lib/docker, currently on root ext4
Missing runtime mount root: /srv/structura
Missing expected runtime dataset tree: tank/structura and all tank/structura/* children from the Structura ZFS matrix
```

Expected Structura runtime datasets still to create before production-equivalent runtime validation, unless an operator intentionally maps them differently:

```text
tank/structura -> /srv/structura
tank/structura/postgres -> /srv/structura/postgres
tank/structura/redis -> /srv/structura/redis
tank/structura/objects-canonical -> /srv/structura/objects/canonical
tank/structura/objects-derived -> /srv/structura/objects/derived
tank/structura/objects-exports -> /srv/structura/objects/exports
tank/structura/models -> /srv/structura/models
tank/structura/staging -> /srv/structura/staging
tank/structura/cache -> /srv/structura/cache
tank/structura/config -> /srv/structura/config
tank/structura/logs -> /srv/structura/logs
tank/structura/backups -> /srv/structura/backups
tank/structura/observability -> /srv/structura/observability
tank/structura/tmp -> /srv/structura/tmp
```

The artifact matrix also lists optional `tank/structura/repo` and `tank/structura/venv`, but the active GPU-node policy supersedes those for source and virtualenv placement: use `/tank/repos/structura` and `/tank/venvs`.
