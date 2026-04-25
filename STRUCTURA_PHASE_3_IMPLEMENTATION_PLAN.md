# Structura Phase 3 Implementation Plan

Phase 3 creates durable structural understanding: complete preview/page assets, Docling canonical parse artifacts, relational page/element/table/chunk rows, parse quality metadata, and an explicit debug surface.

This plan expands Phase 3 from `STRUCTURA_IMPLEMENTATION_PLAN.md`. It does not replace the root plan. Use the root plan for phase boundaries and this document for Phase 3 execution detail.

## Operating Rules

- Do not inspect or rely on anything under `archive/`.
- Before coding any subphase, re-read the files listed in that subphase's **Fresh Context** section. Use `wc -l` and bounded `sed -n` chunks for large files so full reads are auditable.
- When an artifact exists in both Markdown and DOCX form, read the Markdown artifact by default. Only inspect DOCX when the user explicitly asks for layout/fidelity review or the Markdown file is missing/incomplete.
- Keep generated FastAPI OpenAPI paths aligned with `contracts/api/openapi.yaml`. If implementation and contract differ, stop and resolve the contract question explicitly.
- Preserve Phase 0-2 security posture: document, asset, job, organization, debug, and admin routes stay protected; browser-mutating routes require CSRF; logs and job payloads must not contain raw document text, raw model output, sensitive extracted fields, or large prompt bodies.
- Keep Phase 3 focused on preview hardening and canonical parsing. Do not implement classification, schema-specific extraction, model/VLM extraction, embeddings, hybrid search, relationships, analysis, or exports except for explicit placeholders required by existing contracts.
- Treat Docling JSON as the durable canonical structural artifact. Model-specific outputs are later derivatives, not the structural source of truth.
- Derived artifacts may be regenerated, but every generated artifact must remain tied to provenance: job ID, converter name/version, source asset, options/config, and creation time.

## Firecrawl Evidence Rule

When APIs, external contracts, library behavior, security conventions, OpenAPI semantics, FastAPI/Pydantic behavior, PostgreSQL/SQL behavior, Docling APIs, PDF/image tooling, OCR/page rendering behavior, container packaging, React/Vite conventions, Playwright behavior, or UI accessibility conventions are in play, search online with Firecrawl if there is any uncertainty.

Use primary sources where possible: official framework documentation, standards documents, official package docs, project repositories, model cards, or vendor docs. Save Firecrawl outputs under `.firecrawl/`, read them incrementally, and summarize the evidence in implementation notes or ADRs when it affects a decision. Do not use unsourced memory to settle uncertain API, parser, database, browser, worker, or security behavior.

## Phase 3 Required Artifact Set

The full Phase 3 artifact list from `STRUCTURA_IMPLEMENTATION_PLAN.md` remains required context:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/AGENT_START_HERE.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
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

The duplicate DOCX entries in the root plan are intentionally omitted here under the current repo guidance.

## 3.0 Baseline Reconciliation

Goal: confirm Phases 1 and 2 are stable and identify the exact files Phase 3 will change.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 3 section.
- `STRUCTURA_PHASE_1_IMPLEMENTATION_PLAN.md`, preview/object-storage commitments.
- `STRUCTURA_PHASE_2_IMPLEMENTATION_PLAN.md`, document list/detail and UI commitments.
- `agents.md`.
- `.wolf/cerebrum.md`.
- `apps/api/structura_api/routes_documents.py`.
- `lib/jobs/service.py`.
- `lib/storage/`.
- `workers/placeholder.py`.
- `workers/previews/`.
- `workers/docling/`.
- `database/020_core_tables.sql`.
- `contracts/api/openapi.yaml`.

Work:

- Confirm Phase 1 upload/storage/asset streaming and Phase 2 folder/tag/document detail behavior are complete or identify blockers.
- Reconfirm current object storage roots and derived asset behavior.
- Reconfirm current job service behavior: claim, heartbeat, fail, retry, dead-letter, and payload safety.
- Identify whether new job types are represented as free-form `pipeline_jobs.job_type` values or need documented constants.
- Confirm table coverage for `document_assets`, `document_pages`, `document_elements`, `document_tables`, and `document_chunks`.
- Decide whether any additive migration is needed for parse quality metadata, current canonical artifact references, or debug route support. Prefer existing `metadata_json` fields when they are sufficient.

Firecrawl Evidence:

- If PostgreSQL schema constraints, migration ordering, job retry semantics, or current Docling installation/packaging expectations are uncertain, use Firecrawl against primary docs before deciding.

Exit Criteria:

- Phase 3 dependencies are known.
- The implementation file set is identified.
- No schema, contract, or worker-runtime mismatch is left unresolved.

## 3.1 Preview And Page-Asset Hardening

Goal: harden Phase 1 thumbnail/page preview generation into complete, durable page assets.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `3A. Preview And Page-Asset Hardening`.
- `pro-merged-master-v1.2/AGENT_START_HERE.md`, Gates A and B.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, canonical parse and viewer expectations.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, preview/viewer and canonical parsing sections.
- `pro-merged-master-v1.2/docs/08_ZFS_Datasets_and_Storage_Plan.md`, object storage layout.
- `pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv`, `worker-previews`.
- `pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv`, derived object dataset.
- `database/020_core_tables.sql`, `document_assets` and `document_pages`.
- `workers/previews/`.

Work:

- Generate complete page image sets for PDFs and supported image-derived PDFs where Phase 1 only required first-pass previews.
- Store page images and thumbnails as `document_assets` under the derived object root with roles `page_image` and `thumbnail`.
- Link page images and thumbnails through `document_pages.image_asset_id` and `document_pages.thumbnail_asset_id`.
- Keep generated page assets idempotent across re-runs; replace current derived assets by versioning/superseding without deleting history.
- Track source asset ID, source SHA-256, rendering tool/version, rendering options, page number, dimensions, and job ID in metadata.
- Define cache policy and regeneration behavior for stale or missing derived assets.
- Add tests for full-page generation, idempotent rerun, missing-file recovery, unsupported input handling, and DB/filesystem consistency.

Firecrawl Evidence:

- Before changing PDF/image tooling or command flags, use Firecrawl to verify current official documentation and security notes for the selected renderer/library.
- Use Firecrawl if there is uncertainty around image format choice, DPI defaults, transparency handling, PDF page dimensions, or container availability.

Exit Criteria:

- Inbox and Viewer use generated thumbnails/previews.
- Failed preview jobs are visible and retryable.
- All generated previews are cataloged as authorized derived assets.

## 3.2 Preview Worker Orchestration, Cache, And Failure States

Goal: make preview jobs observable, retryable, and safe under partial failure.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `3A. Preview And Page-Asset Hardening`.
- `pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md`, storage sprawl and operational fragility risks.
- `lib/jobs/service.py`.
- `workers/placeholder.py`.
- `workers/previews/`.
- `contracts/events/ingest_document_job.v1.schema.json`.
- `contracts/schemas/common_defs.schema.json`.

Work:

- Add or refine preview job claim/heartbeat/complete/fail flow.
- Ensure preview job payloads include IDs and object metadata only, not raw document text or extracted content.
- Make preview generation transactional at the DB boundary: incomplete generated files must not become current assets.
- Surface preview failure state in job status and document/detail metadata without blocking manual filing.
- Add stale-cache detection and regeneration triggers when source asset hash or renderer version changes.
- Add tests for retryable failure, dead-letter behavior, heartbeat updates, no raw-content payloads, and cleanup after partial writes.

Firecrawl Evidence:

- Use Firecrawl if worker concurrency, file locking, temporary-file cleanup, or retry/backoff conventions need primary-source support.

Exit Criteria:

- Preview jobs can be retried safely.
- Partial preview failures are explicit and recoverable.
- No preview job leaks raw document content into logs or payloads.

## 3.3 Docling Worker Packaging And Runtime Integration

Goal: introduce a real Docling worker path without coupling heavy conversion to the API process.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `3B. Docling Worker`.
- `pro-merged-master-v1.2/docs/10_Architectural_Decision_Record_Summary.md`, ADR-002 and ADR-015.
- `pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md`, canonical structural artifact policy.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, architecture and Docling backbone sections.
- `pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv`, `worker-docling`.
- `compose.yaml`.
- `apps/api/requirements.txt`.
- `workers/docling/`.

Work:

- Add Docling dependency and worker entrypoint using a packaging approach that works locally and in Compose.
- Keep conversion out of FastAPI request handlers; API should only enqueue/observe work.
- Add worker configuration for timeouts, max pages/size if needed, supported MIME types, and optional OCR behavior.
- Expose worker health snapshots consistent with existing worker health patterns.
- Record converter name, converter version, runtime config, and source document metadata.
- Add smoke tests or lightweight worker tests that can run without large model downloads.

Firecrawl Evidence:

- Use Firecrawl to verify current official Docling installation, document converter APIs, CLI behavior, supported formats, and container/runtime requirements before implementing.
- Use Firecrawl before pinning dependency versions or selecting OCR/rendering options.

Exit Criteria:

- A Docling worker can be started and observed.
- `docling_convert` jobs can be claimed by a real worker path.
- The API remains orchestration-centric.

## 3.4 Docling Conversion And Derived Artifact Persistence

Goal: run Docling conversion and persist canonical structural artifacts durably.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `3B. Docling Worker`.
- `pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md`, canonical structural artifact requirements.
- `pro-merged-master-v1.2/docs/08_ZFS_Datasets_and_Storage_Plan.md`, derived artifact storage.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`, storage and provenance language.
- `database/010_types_and_enums.sql`, `asset_role_enum`.
- `database/020_core_tables.sql`, `document_assets` and `documents.canonical_asset_id`.
- `lib/storage/`.
- `workers/docling/`.

Work:

- Convert supported documents into Docling JSON.
- Persist `docling_json` as a derived `document_assets` row.
- Persist optional markdown and optional HTML as `docling_md` and `docling_html` when produced and useful.
- Set or update the current canonical artifact reference without deleting historical derived artifacts.
- Store conversion metadata: converter name/version, options, input hash, job ID, page count, warnings, duration, and parse quality signals available at this stage.
- Ensure failed conversions produce explicit job failure metadata and document metadata without corrupting existing current canonical assets.
- Add tests for successful conversion, conversion failure, rerun superseding, historical artifact preservation, and storage consistency.

Firecrawl Evidence:

- Use Firecrawl if Docling export APIs, output schemas, markdown/HTML generation, provenance fields, or version-reporting APIs are uncertain.

Exit Criteria:

- Every conversion ends with durable artifacts or explicit failure.
- Re-run is idempotent.
- Historical canonical artifacts remain available for debugging.

## 3.5 Canonical-To-Relational Population

Goal: populate pages, elements, tables, and chunks from canonical artifacts.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `3B. Docling Worker`.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, canonical parse requirements.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, database population from canonical artifacts.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, Epic 3 canonical understanding.
- `pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md`, evidence contract.
- `database/020_core_tables.sql`, `document_pages`, `document_elements`, `document_tables`, and `document_chunks`.
- `database/030_constraints_and_triggers.sql`.
- `database/040_indexes_bm25_pgvector.sql`.

Work:

- Create or replace `document_pages` rows with page number, dimensions, rotation, text content, OCR confidence, and page metadata.
- Create `document_elements` rows with page linkage, parent element linkage where possible, type mapping, ordinal, bbox JSON, text/html content, source ref, and confidence.
- Create `document_tables` rows with table JSON, HTML/markdown/OTSL when available, row/column counts, source refs, and confidence.
- Create search-oriented `document_chunks` rows with stable chunk indexes, page ranges, heading paths, text, markdown, char count, token estimate, and metadata.
- Preserve provenance linkages back to canonical artifact IDs and Docling source refs in metadata/source fields.
- Make population idempotent: rerun should replace rows for the current canonical version without duplicating stale pages/elements/chunks.
- Add tests using small fixture outputs for pages, hierarchy, tables, chunks, idempotent rerun, and evidence-locator readiness.

Firecrawl Evidence:

- Use Firecrawl if Docling JSON structure, hierarchy/provenance fields, token counting libraries, chunking conventions, or PostgreSQL upsert/delete-reinsert patterns are uncertain.

Exit Criteria:

- Page/chunk/element/table rows are inspectable.
- DB rows match source artifact structure closely enough for later evidence jumps.
- Chunk rows are ready for Phase 5 search/embedding work without implementing embeddings now.

## 3.6 Parse Quality Heuristics And Routing Metadata

Goal: store quality signals that later phases can use for classification, extraction, visual retrieval, and review.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 3 gate.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, parse quality heuristics.
- `pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md`, parse quality and handwriting risks.
- `pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md`, routing defaults.
- `database/020_core_tables.sql`, `documents.metadata_json` and `document_pages.metadata_json`.

Work:

- Store digital-native vs scanned heuristic.
- Store OCR confidence, text density, page complexity, table density, image-only page flags, and handwriting suspicion where available.
- Store per-document parse status and quality summary in metadata without creating false trust.
- Ensure quality metadata can influence later routing but does not trigger Phase 4 extraction by itself.
- Add tests for quality metadata on digital-native fixture, scanned/image fixture, empty-text fixture, and failed parse fixture.

Firecrawl Evidence:

- Use Firecrawl if OCR confidence semantics, Docling metadata fields, scanned-vs-digital heuristics, or handwriting detection conventions are uncertain.

Exit Criteria:

- Parse quality metadata exists at document and page levels.
- Later phases have routing signals without needing to reinterpret raw artifacts immediately.

## 3.7 Canonical Debug API Surface

Goal: expose canonical parse internals through protected, explicit debug routes or existing detail endpoints.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `3C. Canonical Debug Surface`.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, engineer canonical artifact inspection story.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`, admin/debug state guidance.
- `contracts/api/openapi.yaml`.
- `apps/api/structura_api/routes_documents.py`.
- `apps/api/structura_api/routes_admin.py`.
- `lib/auth/service.py`.

Work:

- Decide whether debug data belongs under a new protected debug route, an admin route, or a flag on document detail. Do not add undocumented public routes without updating the contract intentionally.
- Return page text, element lists, table summaries, chunk summaries, canonical artifact metadata, and job history for a document.
- Gate debug routes behind authenticated/admin or explicit debug capability.
- Keep raw Docling JSON access authorized through the asset API or a protected debug endpoint; never expose internal filesystem paths.
- Add pagination or limits for large documents.
- Add tests for auth, ACL/admin gating, large output limits, missing parse state, and no object URI leakage.

Firecrawl Evidence:

- Use Firecrawl if FastAPI routing, OpenAPI extension behavior, secure debug endpoint conventions, or response pagination conventions are uncertain.

Exit Criteria:

- Engineers can inspect parse output before extraction.
- Debug APIs do not broaden ordinary user data exposure.

## 3.8 Canonical Debug UI

Goal: add quiet debug panels that make parse output inspectable without dominating the product workbench.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `3C. Canonical Debug Surface`.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`, debug panels and evidence workbench guidance.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, document detail advanced panel expectations.
- `pro-merged-master-v1.2/design-language-v1.3.html`.
- `apps/web/src/App.tsx`.
- `apps/web/src/styles.css`.

Work:

- Add debug tabs/panels behind an explicit route, feature flag, or admin/debug mode.
- Show canonical artifact metadata, raw Docling artifact link/view, page text, element list, chunks, tables, parse quality, and document job history.
- Keep main Inbox/Viewer workflow calm; debug UI must be contextual and opt-in.
- Provide clear empty/failed parse states.
- Add Playwright coverage for debug panel visibility, page/element/chunk/table display, failed parse state, and responsive layout sanity.

Firecrawl Evidence:

- Use Firecrawl for uncertain React routing/state, code viewer/JSON rendering, WAI-ARIA tabs/disclosure patterns, or Playwright conventions.

Exit Criteria:

- Parse internals are inspectable from the UI.
- Debug surfaces do not replace the primary document workflow.

## 3.9 Integration, Reprocessing, And Fixture Coverage

Goal: prove preview and canonical parse work end to end, including reruns and failures.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 3 gate.
- `pro-merged-master-v1.2/AGENT_START_HERE.md`, Gate B.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, Epic 3.
- `pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md`.
- `contracts/api/openapi.yaml`.
- `contracts/events/ingest_document_job.v1.schema.json`.
- `tests/`.

Work:

- Add integration tests for upload/existing fixture to preview generation to Docling conversion to relational rows.
- Add fixture coverage for a simple digital PDF, an image/scanned input where practical, a table-bearing document if lightweight, and an unsupported/corrupt file failure.
- Add reprocess test: rerun preview and Docling jobs, supersede current artifacts, preserve history, and avoid duplicate rows.
- Add consistency tests: document page count, asset rows, page rows, table rows, chunks, metadata, and job state all agree.
- Add security tests: debug/canonical assets require auth, no raw content in job payloads/logs, no filesystem URI leaks.
- Add no-model-worker coverage: Docling/preview path works without VLM extraction/model services.

Firecrawl Evidence:

- Use Firecrawl if test fixture generation, PDF creation, Docling test configuration, or Playwright/debug workflow testing behavior is uncertain.

Exit Criteria:

- Canonical parse artifacts and relational rows are durable.
- Parse failures are explicit.
- Reruns are idempotent and preserve useful history.

## 3.10 Contract, Static Analysis, Runtime, And Gate B

Goal: prove Phase 3 is stable before extraction work begins.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 3 gate.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`.
- `Makefile`.
- `pyproject.toml`.
- `package.json`.
- `apps/web/package.json`.
- `tests/`.
- `compose.yaml`.

Work:

- Run formatting and lint checks.
- Run mypy/pyright/SAST checks using the repo targets.
- Run OpenAPI/schema/event contract validation.
- Run backend unit and integration tests.
- Run worker tests for previews and Docling.
- Run web build.
- Run Playwright UI workflow and screenshot validation for viewer/debug surfaces.
- Run local Compose smoke where practical: API health, worker health, upload/list/detail from Phase 1, folder/tag from Phase 2, preview job, Docling job, debug surface.
- Confirm Gate B from `AGENT_START_HERE.md`: Docling conversion produces persisted canonical artifacts, and page/chunk rows are created correctly.
- Document intentional deferrals: classification, extraction, candidate/canonical field promotion, embeddings, search ranking, visual retrieval, relationships, analysis, and exports.

Firecrawl Evidence:

- If a gate fails due to tool behavior, dependency behavior, Docling behavior, PDF/image behavior, browser/API semantics, SQL behavior, or security convention that is not locally obvious, use Firecrawl to find primary-source evidence before changing code.

Exit Criteria:

- Canonical parse artifacts and relational rows are durable.
- Parse failures are explicit and reviewable.
- Gate B passes before Phase 4 extraction begins.

## Stop Point

Stop after Phase 3 gate validation and report:

- Files changed.
- Tests and checks run.
- Any deferred work and the phase it belongs to.
- Any Firecrawl-sourced evidence that materially shaped implementation decisions.

Do not continue into Phase 4 without explicit user instruction.
