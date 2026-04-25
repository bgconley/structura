# Structura Phase 1 Implementation Plan

Phase 1 builds the first trustworthy filing-cabinet workflow: upload, Inbox, row selection, protected asset access, and the first document viewer. The first working screen is Inbox.

This plan expands Phase 1 from `STRUCTURA_IMPLEMENTATION_PLAN.md`. It does not replace the root plan. Use the root plan for phase boundaries and this document for Phase 1 execution detail.

## Operating Rules

- Do not inspect or rely on anything under `archive/`.
- Before coding any subphase, re-read the files listed in that subphase's **Fresh Context** section. Use `wc -l` and bounded `sed -n` chunks for large files so full reads are auditable.
- When an artifact exists in both Markdown and DOCX form, read the Markdown artifact by default. Only inspect DOCX when the user explicitly asks for layout/fidelity review or the Markdown file is missing/incomplete.
- Keep generated FastAPI OpenAPI paths aligned with `contracts/api/openapi.yaml`. If implementation and contract differ, stop and resolve the contract question explicitly.
- Preserve the Phase 0 security posture: document, asset, job, and admin routes stay protected; browser-mutating routes require CSRF; logs and job payloads must not contain raw document text, raw model output, sensitive extracted fields, or large prompt bodies.
- Implement narrow, testable slices. Do not build Phase 2 filing, Phase 3 Docling parsing, or later model workflows except for minimal placeholders needed to satisfy Phase 1 interfaces.
- UI work must follow `STRUCTURA_UI_FIGMA_QA_PLAN.md`, the Figma frames named there, and the v1.3 design language artifacts.

## Firecrawl Evidence Rule

When APIs, external contracts, library behavior, security conventions, browser behavior, MIME/PDF/image handling, OpenAPI semantics, FastAPI/Starlette behavior, React/Vite conventions, Playwright behavior, or filesystem safety rules are in play, search online with Firecrawl if there is any uncertainty.

Use primary sources where possible: official framework documentation, standards documents, official package docs, or project repositories. Save Firecrawl outputs under `.firecrawl/`, read them incrementally, and summarize the evidence in the implementation notes or ADR when it affects a decision. Do not use unsourced memory to settle uncertain API or security behavior.

## Phase 1 Required Artifact Set

The full Phase 1 artifact list from `STRUCTURA_IMPLEMENTATION_PLAN.md` remains required context:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/AGENT_START_HERE.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
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

The duplicate DOCX entries in the root plan are intentionally omitted here under the current repo guidance.

## 1.0 Baseline Reconciliation

Goal: confirm the Phase 0 surface is stable and identify the exact files Phase 1 will change.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 1 section.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`.
- `agents.md`.
- `.wolf/cerebrum.md`.
- `docs/adr/0000-phase-0-baseline.md`.
- `apps/api/structura_api/routes_documents.py`.
- `apps/web/src/App.tsx`.
- `apps/web/src/styles.css`.
- `contracts/api/openapi.yaml`.

Work:

- Confirm Phase 0 checks still pass before feature work: lint, type, contracts, tests, and web build.
- Reconfirm current route skeletons for `/api/v1/documents`, `/api/v1/documents/{documentId}`, and `/api/v1/assets/{assetId}`.
- Identify DB tables already present from baseline migrations and avoid adding duplicate schema objects.
- Decide whether Phase 1 needs small additive migrations. Prefer existing baseline columns if they already cover the requirement.

Exit Criteria:

- Current baseline is known.
- Phase 1 work files are identified.
- Any contract mismatch is documented before implementation starts.

## 1.1 Object Storage Service

Goal: implement content-addressed filesystem storage for immutable originals and derived artifacts.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `1A. Object Storage`.
- `pro-merged-master-v1.2/docs/08_ZFS_Datasets_and_Storage_Plan.md`.
- `pro-merged-master-v1.2/docs/09_Deployment_and_Runtime_Architecture.md`.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`.
- `pro-merged-master-v1.2/database/020_core_tables.sql`, especially `document_assets`.
- `pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql`, especially household ACL projection.
- `lib/config/settings.py`.

Work:

- Add a storage module under `lib/storage/` for canonical, derived, and export roots from `Settings`.
- Stream uploaded bytes to a temporary file while computing SHA-256.
- Commit originals to a content-addressed path below `canonical_objects_root`, using atomic moves where the filesystem supports them.
- Enforce original immutability: existing content-addressed originals must not be overwritten with different bytes.
- Add storage metadata helpers that return internal object URIs for DB storage and never expose filesystem paths directly to browser clients.
- Add consistency checks to verify DB `document_assets` rows match filesystem existence, size, and hash.
- Add unit tests for hashing, dedupe, immutable writes, object URI parsing, and missing-file detection.

Firecrawl Evidence:

- If uncertain about Python atomic file replace behavior, MIME sniffing libraries, path traversal hardening, or safe temporary-file patterns, use Firecrawl to verify against official Python/library documentation before coding.

Exit Criteria:

- Original bytes can be written, retrieved internally, and hash-verified.
- Duplicate file hashes are detected without silent document merge.
- No path traversal or object URI leakage path exists.

## 1.2 Upload API And Ingest Job Creation

Goal: implement multipart `POST /api/v1/documents` and make uploaded documents appear in Inbox immediately.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `1B. Upload API And Ingest Kickoff`.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, paths `/api/v1/documents` and schemas `UploadDocumentMultipartRequest`, `AcceptedJob`, `DocumentSummary`.
- `pro-merged-master-v1.2/contracts/events/ingest_document_job.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/common_defs.schema.json`.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, ingestion workflow and source preservation sections.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, upload/original preservation stories.
- `pro-merged-master-v1.2/docs/16_Auth_ACL_Household_Model.md`.
- `database/020_core_tables.sql`, `ingest_batches`, `documents`, `document_assets`, `pipeline_jobs`.
- `lib/jobs/service.py`.
- `apps/api/structura_api/dependencies.py`.

Work:

- Replace the `501` upload placeholder with a protected multipart endpoint.
- Accept the contract source enum values: `web_upload`, `api_upload`, `mobile_scan`, `watched_folder`, `email_import`, and `bulk_import`; only `web_upload` needs full UI support in Phase 1.
- Validate MIME type, file extension where useful, size, empty file uploads, and malformed `hintsJson`.
- Create `ingest_batches`, `documents`, `document_assets`, and `pipeline_jobs` transactionally.
- Ensure partial failures leave no dangling DB rows or orphaned temp files.
- Queue an ingest job using the existing safe job service. Payload may include document ID, asset ID, batch ID, source, object URI, filename, MIME type, size, and SHA-256. It must not include raw document text or extracted content.
- Return `AcceptedJob` with the created job ID and queued/running status consistent with the contract.
- Add API tests for auth required, CSRF required for browser cookie auth, successful upload, invalid MIME/size/hints, duplicate hash behavior, and rollback on injected failure.

Firecrawl Evidence:

- Verify FastAPI/Starlette multipart upload behavior, `UploadFile` streaming semantics, and content-length limits with official docs if any uncertainty remains.
- Use Firecrawl before choosing or adding MIME detection dependencies.

Exit Criteria:

- Upload returns document/job identifiers.
- Uploaded document appears in `/api/v1/documents` without waiting for Docling or extraction.
- Contract validation still passes.

## 1.3 Document Listing And Detail API

Goal: return real document summaries and first-pass document detail data for Inbox and Viewer.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 1 done/gate items.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, `DocumentSummary`, `DocumentDetail`, `DocumentAsset`, and `DocumentPage`.
- `pro-merged-master-v1.2/database/050_views_and_functions.sql`, document summary/review views.
- `pro-merged-master-v1.2/database/020_core_tables.sql`, document and asset tables.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`, document trust/state language.
- `apps/api/structura_api/routes_documents.py`.

Work:

- Implement `GET /api/v1/documents` with real DB data, total count, limit, offset, and contract filters currently in scope.
- Map DB rows to the contract casing: `lifecycleState`, `reviewStatus`, `documentDate`, `amountTotal`, `counterpartyDisplay`, `thumbnailUrl`, `folderPaths`.
- Implement `GET /api/v1/documents/{documentId}` with document summary data, assets, and empty-but-valid arrays for Phase 1-not-yet-ready structures such as fields, line items, relationships, extractions, and tags.
- Ensure all returned asset URLs are authorized API URLs such as `/api/v1/assets/{assetId}`.
- Enforce household/ACL scoping through the current principal. Do not expose another household's documents.
- Add tests for list filters, pagination, detail shape, missing document `404`, and authorization boundaries.

Firecrawl Evidence:

- If OpenAPI schema composition, Pydantic serialization, SQL pagination conventions, or FastAPI response model behavior becomes ambiguous, use Firecrawl against official docs before settling the implementation.

Exit Criteria:

- Inbox can render real uploaded documents.
- Document detail can drive the Viewer without object-store URI leakage.
- OpenAPI path parity remains exact.

## 1.4 Protected Asset Streaming

Goal: implement authorized `GET /api/v1/assets/{assetId}` for originals and derived preview assets.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `1D. Protected Asset Viewer`.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, `/api/v1/assets/{assetId}` and `DocumentAsset.assetUrl`.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`.
- `pro-merged-master-v1.2/docs/16_Auth_ACL_Household_Model.md`.
- `pro-merged-master-v1.2/docs/08_ZFS_Datasets_and_Storage_Plan.md`.
- `database/020_core_tables.sql`, `document_assets`.
- `lib/storage/`.

Work:

- Resolve asset IDs through DB ownership/ACL checks before touching the filesystem.
- Stream bytes through the API with correct `Content-Type`, safe `Content-Disposition`, and cache policy.
- Return `404` for missing or unauthorized assets without leaking existence across principals.
- Ensure internal object URIs and filesystem paths never appear in API responses or logs.
- Add tests for authorized download, unauthorized access, missing DB row, missing file, MIME headers, and filename header safety.

Firecrawl Evidence:

- Use Firecrawl to verify Starlette/FastAPI streaming response behavior, content-disposition filename escaping, range request support if considered, and secure download header conventions.

Exit Criteria:

- Original download is routed through authorized API.
- No object-store URI leaks into browser.
- Asset access is auditable and protected.

## 1.5 Preview And Thumbnail Minimum Viable Worker

Goal: generate enough previews for Phase 1 Inbox and Viewer while leaving full Phase 3 parse hardening for later.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `1D. Protected Asset Viewer`, plus the Phase 3 note that hardening continues later.
- `pro-merged-master-v1.2/AGENT_START_HERE.md`, Gate A.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, upload/preview milestones.
- `pro-merged-master-v1.2/docs/08_ZFS_Datasets_and_Storage_Plan.md`.
- `pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv`.
- `pro-merged-master-v1.2/infrastructure/zfs/dataset_matrix.csv`.
- `database/020_core_tables.sql`, `document_pages`, `document_assets`.
- `workers/previews/`.

Work:

- Add a preview worker or service function that can create a thumbnail and first page preview for common Phase 1 inputs.
- Store previews as derived assets under `derived_objects_root`.
- Insert/update `document_pages` and link `image_asset_id` and/or `thumbnail_asset_id` where schema permits.
- Make preview generation idempotent and retryable through `pipeline_jobs`.
- Keep failures visible in job state without blocking the document from appearing in Inbox.
- Add tests with a small fixture document/image for successful preview, idempotent rerun, and failed preview job state.

Firecrawl Evidence:

- Before choosing PDF/image tooling or command flags, use Firecrawl to verify current official documentation and security notes for the selected library/tool.
- If using external binaries, verify macOS/local and container availability assumptions before coding around them.

Exit Criteria:

- Uploaded documents can show a thumbnail or stable fallback state.
- Viewer can display a first-page preview or a clearly handled unsupported-preview state.
- Phase 3 still owns complete page image sets and Docling artifact persistence.

## 1.6 Inbox UI From Figma Frame `17:2`

Goal: replace the placeholder web shell with the Figma-aligned Inbox using real API data where available.

Fresh Context:

- `STRUCTURA_UI_FIGMA_QA_PLAN.md`.
- `pro-merged-master-v1.2/design-language-v1.3.html`.
- `pro-merged-master-v1.2/design-language-dashboard.PNG`.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, document list/detail schemas.
- `apps/web/src/App.tsx`.
- `apps/web/src/styles.css`.

Work:

- Implement the Inbox as the default route after sign-in.
- Match Figma frame `17:2`: shell, sidebar, top bar, metrics, document table, status chips, machine health block, pipeline summary, and right evidence inspector.
- Use real API data for uploaded documents, selection state, document detail, asset URLs, job status where available, and stable mock data only where backend stages are intentionally later.
- Implement upload entry point in the UI using the Phase 1 upload endpoint.
- Keep controls feature-complete for expected Phase 1 workflows: upload, select row, open viewer, refresh, filter chips where supported, and evidence inspector state.
- Add UI tests for initial load, upload success path, row selection, inspector update, and open viewer.

Firecrawl Evidence:

- Use Firecrawl for uncertain React/Vite, browser file upload, fetch/credentials, CSRF header, or Playwright API behavior. Prefer official docs.

Exit Criteria:

- Inbox displays uploaded documents.
- Selecting a row updates the inspector.
- Processing state is visible.
- The UI follows the Figma/design artifacts rather than the placeholder shell.

## 1.7 Protected Document Viewer From Figma Frame `14:434`

Goal: let the user open a document from Inbox and inspect the original/preview and Phase 1 metadata.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `1D. Protected Asset Viewer`.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`.
- `pro-merged-master-v1.2/design-language-v1.3.html`.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, document detail and asset schemas.
- `apps/web/src/App.tsx`.
- `apps/web/src/styles.css`.

Work:

- Implement a Viewer route or state from Inbox using Figma frame `14:434`.
- Show thumbnails, main document page/preview, document facts, trust state, key fields placeholder state, and actions appropriate to Phase 1.
- Route original download through `/api/v1/assets/{assetId}`.
- Represent not-yet-available extraction fields as empty or pending states, not fabricated model results.
- Preserve responsive behavior and no-overlap constraints from the UI QA plan.
- Add UI tests for opening a document, rendering preview/unsupported state, downloading through authorized URL, and returning to Inbox.

Firecrawl Evidence:

- Use Firecrawl for uncertain browser PDF/image rendering, object URL handling, download behavior, or accessibility conventions.

Exit Criteria:

- User can open a document from Inbox into Viewer.
- Viewer uses authorized asset URLs.
- Empty extraction state is honest and aligned with Phase 1 scope.

## 1.8 Phase 1 Integration Workflow

Goal: make upload, list, select, inspect, view, and download work as one flow.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 1 gate.
- `pro-merged-master-v1.2/AGENT_START_HERE.md`, Gate A.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`.
- `contracts/api/openapi.yaml`.
- `contracts/events/ingest_document_job.v1.schema.json`.
- `tests/`.

Work:

- Add integration tests covering authenticated upload, DB rows, filesystem object, job creation, list visibility, detail retrieval, asset streaming, and preview state.
- Add frontend workflow tests for upload through UI, row selection, inspector, viewer, and protected asset use.
- Ensure no raw content is included in logs or job payloads.
- Confirm rollback behavior on failed storage, failed DB insert, and failed job enqueue.
- Confirm duplicate upload semantics match the Phase 1 requirement: duplicate file hashes are detected without silent merge.

Firecrawl Evidence:

- Use Firecrawl if test harness behavior, multipart test clients, Playwright file upload, or security expectations need verification.

Exit Criteria:

- The workflow succeeds locally from UI to API to DB/storage and back.
- Negative-path tests cover the security and consistency risks.

## 1.9 Contract, Static Analysis, Runtime, And UI Gate

Goal: prove Phase 1 is stable before regrouping.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 1 gate.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`.
- `Makefile`.
- `pyproject.toml`.
- `package.json`.
- `apps/web/package.json`.
- `tests/`.

Work:

- Run formatting and lint checks.
- Run mypy/pyright/SAST checks using the repo targets.
- Run OpenAPI/schema/event contract validation.
- Run backend unit and integration tests.
- Run web build.
- Run Playwright UI workflow and screenshot validation against Figma/dashboard references.
- Run local Compose smoke where practical: API health, auth, upload, list, asset, web route.
- Document any intentional deferrals to Phase 2 or Phase 3.

Firecrawl Evidence:

- If a gate fails due to tool behavior, dependency behavior, or browser/API semantics that are not locally obvious, use Firecrawl to find primary-source evidence before changing code.

Exit Criteria:

- Upload, Inbox, row selection, inspector, and Viewer work.
- Originals are immutable and retrievable.
- Thumbnail generation works or unsupported previews are explicitly handled with retryable jobs.
- Playwright validates the workflow and screenshot state.
- Gate A from `AGENT_START_HERE.md` passes.

## Stop Point

Stop after Phase 1 gate validation and report:

- Files changed.
- Tests and checks run.
- Any deferred work and the phase it belongs to.
- Any Firecrawl-sourced evidence that materially shaped implementation decisions.

Do not continue into Phase 2 without explicit user instruction.
