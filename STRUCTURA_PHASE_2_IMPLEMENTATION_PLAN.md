# Structura Phase 2 Implementation Plan

Phase 2 makes Structura useful as a manual filing cabinet before AI extraction: folders, tags, document organization edits, primary-folder behavior, and visible folder/tag surfaces.

This plan expands Phase 2 from `STRUCTURA_IMPLEMENTATION_PLAN.md`. It does not replace the root plan. Use the root plan for phase boundaries and this document for Phase 2 execution detail.

## Operating Rules

- Do not inspect or rely on anything under `archive/`.
- Before coding any subphase, re-read the files listed in that subphase's **Fresh Context** section. Use `wc -l` and bounded `sed -n` chunks for large files so full reads are auditable.
- When an artifact exists in both Markdown and DOCX form, read the Markdown artifact by default. Only inspect DOCX when the user explicitly asks for layout/fidelity review or the Markdown file is missing/incomplete.
- Keep generated FastAPI OpenAPI paths aligned with `contracts/api/openapi.yaml`. If implementation and contract differ, stop and resolve the contract question explicitly.
- Preserve Phase 0 and Phase 1 security posture: document, asset, job, organization, and admin routes stay protected; browser-mutating routes require CSRF; logs must not contain raw document text or sensitive extracted content.
- Keep Phase 2 focused on manual organization. Do not implement contacts, filing-rule automation, watched-folder ingestion, search ranking, Docling parsing, extraction, or model workflows except for explicit placeholders required by existing contracts.
- UI work must follow `STRUCTURA_UI_FIGMA_QA_PLAN.md`, the Figma frames named there, and the v1.3 design language artifacts. Folder/tag filing workflow is the third UI priority slice after upload/Inbox/Viewer and review/evidence surfaces.

## Firecrawl Evidence Rule

When APIs, external contracts, library behavior, security conventions, OpenAPI semantics, FastAPI/Pydantic behavior, PostgreSQL/SQL behavior, React/Vite conventions, Playwright behavior, or UI accessibility conventions are in play, search online with Firecrawl if there is any uncertainty.

Use primary sources where possible: official framework documentation, standards documents, official package docs, or project repositories. Save Firecrawl outputs under `.firecrawl/`, read them incrementally, and summarize the evidence in implementation notes or ADRs when it affects a decision. Do not use unsourced memory to settle uncertain API, database, browser, or security behavior.

## Phase 2 Required Artifact Set

The full Phase 2 artifact list from `STRUCTURA_IMPLEMENTATION_PLAN.md` remains required context:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
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

The duplicate DOCX entries in the root plan are intentionally omitted here under the current repo guidance.

## 2.0 Baseline Reconciliation

Goal: confirm Phase 1 is stable and identify the exact files Phase 2 will change.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 2 section.
- `STRUCTURA_PHASE_1_IMPLEMENTATION_PLAN.md`, especially the Phase 1 stop point and any Phase 1 implementation notes.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`.
- `agents.md`.
- `.wolf/cerebrum.md`.
- `apps/api/structura_api/routes_documents.py`.
- `apps/web/src/App.tsx`.
- `apps/web/src/styles.css`.
- `contracts/api/openapi.yaml`.
- `database/README.md`.

Work:

- Confirm the Phase 1 gate is complete or explicitly identify Phase 1 prerequisites that Phase 2 depends on.
- Reconfirm current route skeletons for `/api/v1/folders`, `/api/v1/tags`, and `/api/v1/documents/{documentId}/organization`.
- Identify whether `060_seed_taxonomies.sql` already runs in the baseline migration plan. If not, add it through the normal migration mechanism rather than ad hoc boot scripts.
- Confirm the existing schema has all required Phase 2 tables and columns: `folders`, `document_folder_memberships`, `tags`, `document_tags`, `saved_searches`, `folder_acl`, `documents.primary_folder_id`, `documents.filing_notes`, `documents.title`, and `documents.document_date`.
- Decide whether any additive migration is necessary for audit events or path maintenance. Prefer existing baseline objects if they cover the requirement.

Firecrawl Evidence:

- If migration ordering, PostgreSQL `citext` uniqueness, `ltree` path handling, or OpenAPI path parity behavior is uncertain, use Firecrawl against primary docs before deciding.

Exit Criteria:

- Phase 2 dependencies are known.
- The implementation file set is identified.
- No schema or contract mismatch is left unresolved.

## 2.1 Taxonomy Seeds And Organization Read Models

Goal: make seeded folders/tags and organization projections reliable before adding write APIs.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 2 tasks and gate.
- `pro-merged-master-v1.2/database/060_seed_taxonomies.sql`.
- `pro-merged-master-v1.2/database/020_core_tables.sql`, `folders`, `document_folder_memberships`, `tags`, `document_tags`, and `saved_searches`.
- `pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql`, folder household/owner/ACL extensions.
- `pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql`, folder/tag indexes.
- `pro-merged-master-v1.2/database/050_views_and_functions.sql`, `document_folder_paths_v` and `document_summary_v`.
- `database/README.md`.
- `lib/db/migrations.py`.

Work:

- Ensure system folders and system tags seed idempotently in local test and integration databases.
- Ensure seeded folders receive household/owner context where the current auth model requires it.
- Define a canonical folder path strategy for nested folders using `path_cache` and `path_ltree` where available.
- Add or update read helpers for folder tree shape, tag list shape, and document summary folder/tag projection.
- Confirm `document_summary_v` or the application read model exposes folder and tag values used by Inbox, Viewer, and Folder pages.
- Add tests for seed idempotency, path computation, duplicate folder names under the same parent, duplicate tag names, and empty-state read models.

Firecrawl Evidence:

- Use Firecrawl if PostgreSQL `ltree`, `citext`, recursive folder path queries, or migration idempotency behavior is uncertain.

Exit Criteria:

- Seeded folders and tags are present after migration.
- Folder/tag reads have stable ordering.
- Existing document list/detail APIs can include folder/tag data without ad hoc joins in the UI.

## 2.2 Folders API

Goal: implement contract-aligned folder listing and creation for manual and smart folders.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 2 tasks.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, `/api/v1/folders`, `Folder`, and `FolderWrite`.
- `pro-merged-master-v1.2/contracts/schemas/folder_acl.v1.schema.json`.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, filing and organization section.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, Story 2.2 and Story 2.3.
- `pro-merged-master-v1.2/docs/16_Auth_ACL_Household_Model.md`, folder ACL and inheritance rules.
- `database/020_core_tables.sql`, `folders` and `saved_searches`.
- `apps/api/structura_api/routes_documents.py`.

Work:

- Replace the `501` `POST /api/v1/folders` placeholder with a CSRF-protected implementation.
- Implement `GET /api/v1/folders` with household/ACL scoping, stable ordering, and contract shape.
- Support nested manual folders through `parentId`.
- Support smart folders through `folderKind=smart` and `savedQuery`, while keeping actual advanced search execution deferred to later search phases unless needed for the UI.
- Validate folder names, parent existence, cycles, duplicate sibling names, and `aclMode`.
- Store `path_cache` and `path_ltree` consistently for manual and smart folders.
- Return contract fields: `id`, `parentId`, `folderKind`, `name`, `path`, `savedQuery`, and `aclMode`.
- Add tests for auth, CSRF, nested creation, smart folder creation, invalid parent, duplicate sibling, ACL scoping, and contract serialization.

Firecrawl Evidence:

- Use Firecrawl if FastAPI body validation, Pydantic aliasing/casing, PostgreSQL recursive query patterns, or ACL response conventions are uncertain.

Exit Criteria:

- Folders can be created and listed.
- Nested folders are supported.
- Smart folder records can be created without implying Phase 5 search execution is complete.

## 2.3 Tags API

Goal: implement contract-aligned tag listing and creation.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 2 tasks.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, `/api/v1/tags`, `Tag`, and `TagWrite`.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, manual organization section.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, Story 2.2.
- `pro-merged-master-v1.2/database/020_core_tables.sql`, `tags` and `document_tags`.
- `pro-merged-master-v1.2/database/060_seed_taxonomies.sql`.
- `apps/api/structura_api/routes_documents.py`.

Work:

- Replace the `501` `POST /api/v1/tags` placeholder with a CSRF-protected implementation.
- Implement `GET /api/v1/tags` with stable ordering and contract shape.
- Validate tag names, color hex values, duplicate names, and description length.
- Decide whether tags are global to the local install or household scoped. If the current schema is global, document that Phase 2 keeps schema behavior and defers household-scoped tags unless a contract/schema update is approved.
- Return contract fields: `id`, `name`, `colorHex`, and `description`.
- Add tests for auth, CSRF, create/list, duplicate case-insensitive names, invalid color, seeded tags, and contract serialization.

Firecrawl Evidence:

- Use Firecrawl if CSS color validation, case-insensitive uniqueness, or Pydantic validation behavior is uncertain.

Exit Criteria:

- Tags can be created and listed.
- Seeded tags and user-created tags coexist.
- API responses match the OpenAPI contract.

## 2.4 Document Organization Update API

Goal: implement `POST /api/v1/documents/{documentId}/organization` for manual filing and metadata edits.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 2 tasks and done criteria.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, `/api/v1/documents/{documentId}/organization`, `DocumentOrganizationWrite`, and `DocumentDetail`.
- `pro-merged-master-v1.2/contracts/schemas/review_action.v1.schema.json`, organization action types.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, filing and document detail expectations.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, Story 2.2.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`, document table and evidence inspector action expectations.
- `database/020_core_tables.sql`, `documents`, `document_folder_memberships`, and `document_tags`.
- `database/050_views_and_functions.sql`, `document_summary_v`.
- `apps/api/structura_api/routes_documents.py`.

Work:

- Replace the `501` organization update placeholder with a CSRF-protected implementation.
- Support partial updates for `title`, `documentDate`, `folderIds`, `primaryFolderId`, `tags`, and `filingNotes`.
- Allow multiple folder memberships.
- Enforce that `primaryFolderId`, when supplied, is one of the document's folder memberships or is atomically added according to the chosen policy.
- Ensure only one primary folder is true per document.
- Resolve `tags` by name according to the contract. Create missing tags only if the product decision explicitly allows it; otherwise reject unknown tags with a clear `422`.
- Recompute document list/detail projections after update.
- Return updated `DocumentDetail`.
- Add tests for partial metadata update, multi-folder assignment, primary folder behavior, tag assignment/removal, unknown folder, unknown tag policy, unauthorized document, and transaction rollback.

Firecrawl Evidence:

- Use Firecrawl if PostgreSQL transaction isolation, upsert/delete synchronization patterns, JSON request validation, or FastAPI error semantics are uncertain.

Exit Criteria:

- Documents can be filed manually.
- One document can belong to multiple folders.
- Title, document date, notes, primary folder, folders, and tags update atomically.

## 2.5 Audit And ACL Enforcement

Goal: make organization changes safe, scoped, and auditable where appropriate.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 2 done criteria.
- `pro-merged-master-v1.2/docs/16_Auth_ACL_Household_Model.md`.
- `pro-merged-master-v1.2/contracts/schemas/folder_acl.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/review_action.v1.schema.json`.
- `pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql`, `folder_acl`, `audit_events`, and `review_events`.
- `pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql`, audit/review indexes.
- `apps/api/structura_api/dependencies.py`.
- `lib/auth/service.py`.

Work:

- Enforce household membership on folder, tag, and document organization routes.
- Enforce folder ACL for reads and writes where the current schema and auth model support it.
- Do not expose whether inaccessible folders/documents exist.
- Record audit events for organization changes where appropriate: folder membership changes, primary folder changes, tag changes, title/date/notes changes, and ACL changes if implemented in this phase.
- Use review action semantics for move/add/remove actions only if the existing schema supports it cleanly; otherwise use `audit_events` and document review-action integration as a Phase 4 concern.
- Add tests for cross-household access denial, private/custom folder behavior, failed access behavior, and audit rows.

Firecrawl Evidence:

- Use Firecrawl if authorization response conventions, secure `404` vs `403` behavior, or audit logging patterns are uncertain. Prefer OWASP, framework, or official documentation.

Exit Criteria:

- Folder/document organization respects household scope.
- Organization writes are auditable.
- Asset/document authorization behavior remains compatible with Phase 1.

## 2.6 Document List, Detail, And Filter Propagation

Goal: make folders and tags visible everywhere Phase 2 users expect them.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 2 done criteria.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, `DocumentSummary`, `DocumentDetail`, `Folder`, `Tag`, and `DocumentOrganizationWrite`.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, major views and search/filter expectations.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`, document table, inspector, and status chip expectations.
- `database/050_views_and_functions.sql`, `document_summary_v`.
- `apps/api/structura_api/routes_documents.py`.

Work:

- Ensure `GET /api/v1/documents` includes folder paths and supports `folderId` filtering.
- Ensure `GET /api/v1/documents/{documentId}` includes tags, folder paths, primary folder state, and filing notes where the contract permits.
- Decide whether to extend the contract for richer folder/tag detail in document detail. If needed, update contract and validation tests deliberately rather than adding undocumented fields.
- Add any missing server-side mapping needed by Inbox, Viewer, Folders page, and folder/tag edit controls.
- Add tests for document list folder filter, tag display in detail, folder path display, unfiled document behavior, and no-model-worker behavior.

Firecrawl Evidence:

- Use Firecrawl if OpenAPI additional-properties constraints, response model extension rules, or SQL filtering patterns are uncertain.

Exit Criteria:

- Folders and tags appear in document lists and detail.
- Folder filtering works for manual folders.
- Smart folder display exists even if advanced smart-folder execution is deferred.

## 2.7 Folder And Tag UI

Goal: add the manual filing UI surfaces expected for Phase 2.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 2 tasks.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`.
- `pro-merged-master-v1.2/design-language-v1.3.html`.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, major views and document detail expectations.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, folder/tag/document organization schemas.
- `apps/web/src/App.tsx`.
- `apps/web/src/styles.css`.

Work:

- Add a Folders surface with hierarchical manual folders and visible smart folders.
- Add tag creation and tag picker surfaces.
- Add document edit actions in Inbox/Viewer/inspector: file document, edit title/date/notes, assign folders, choose primary folder, and apply/remove tags.
- Keep selected document context stable while folder/tag filters change.
- Show unfiled state and filed state clearly with accessible text.
- Preserve design constraints: calm evidence workbench, dense but readable operational UI, compact controls, no overlapping text, and no unrelated marketing sections.
- Add Playwright tests for folder tree, create folder, create tag, file document, tag document, primary folder selection, and mobile/desktop layout sanity.

Firecrawl Evidence:

- Use Firecrawl for uncertain React state management, browser form behavior, Playwright locators/file state, WAI-ARIA tree/listbox patterns, or accessibility conventions. Prefer official React, Playwright, and WAI-ARIA sources.

Exit Criteria:

- Folder and tag UI works against real APIs.
- Documents can be manually filed without model workers.
- Folders/tags are visible in the document list and viewer.

## 2.8 Smart Folder And Saved Query Baseline

Goal: preserve the smart-folder contract while avoiding premature Phase 5 search implementation.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 2 and Phase 5 boundaries.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, Story 2.3.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, derived organization and search expectations.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, `Folder.folderKind`, `Folder.savedQuery`, and `FolderWrite.savedQuery`.
- `database/020_core_tables.sql`, `folders` and `saved_searches`.
- `database/050_views_and_functions.sql`.

Work:

- Support creating and listing smart-folder records with `savedQuery`.
- Define a minimal query JSON validation policy for Phase 2 that rejects malformed saved query objects but does not implement full search grammar.
- Render smart folders separately from manual folders in UI.
- Seed existing smart folders from `060_seed_taxonomies.sql`.
- Document that dynamic smart-folder execution over full search/filter grammar remains Phase 5 unless Phase 2 implements a narrow local filter such as `review_status`.
- Add tests for smart-folder create/list, malformed saved query rejection, seeded smart folders, and UI rendering.

Firecrawl Evidence:

- Use Firecrawl if JSON Schema validation options, OpenAPI object typing, or client-side saved-query editing conventions are uncertain.

Exit Criteria:

- Smart folders are first-class records.
- Phase 2 does not falsely claim full advanced search is complete.

## 2.9 Phase 2 Integration Workflow

Goal: prove manual filing works end to end with model workers disabled.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 2 gate.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, manual filing baseline.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, organization stories.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, if organization audit/security questions arise.
- `contracts/api/openapi.yaml`.
- `tests/`.

Work:

- Add integration tests for create folder, create tag, upload or use an existing document fixture, assign folders/tags, set primary folder, edit metadata, list by folder, open detail, and verify audit.
- Add no-model-worker smoke coverage: disable model placeholders/workers and confirm manual filing still works.
- Confirm all mutating organization requests require CSRF under browser cookie auth.
- Confirm API-token automation behavior for organization routes if Phase 0 API-token scope support is active.
- Confirm rollback behavior for invalid folder/tag updates and partial write failures.

Firecrawl Evidence:

- Use Firecrawl if test-client CSRF behavior, API-token conventions, or transaction rollback patterns need confirmation.

Exit Criteria:

- Manual filing works end to end.
- Negative-path tests cover auth, CSRF, ACL, validation, and rollback risks.

## 2.10 Contract, Static Analysis, Runtime, And UI Gate

Goal: prove Phase 2 is stable before regrouping.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 2 gate.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`.
- `Makefile`.
- `pyproject.toml`.
- `package.json`.
- `apps/web/package.json`.
- `tests/`.

Work:

- Run formatting and lint checks.
- Run mypy/pyright/SAST checks using the repo targets.
- Run OpenAPI/schema contract validation.
- Run backend unit and integration tests.
- Run web build.
- Run Playwright UI workflow and screenshot validation for folder/tag filing flows.
- Run local Compose smoke where practical: API health, auth, upload/list/detail from Phase 1, folder create/list, tag create/list, document organization update, web route.
- Document intentional deferrals: contacts, filing-rule automation, watched-folder ingestion, full search grammar, dynamic smart-folder execution, extraction review workflows, and model-based filing suggestions.

Firecrawl Evidence:

- If a gate fails due to tool behavior, dependency behavior, browser/API semantics, SQL behavior, or security convention that is not locally obvious, use Firecrawl to find primary-source evidence before changing code.

Exit Criteria:

- Documents can be filed manually.
- Folders and tags appear in document lists and detail.
- Organization changes are protected and auditable where appropriate.
- Manual filing works when all model workers are disabled.

## Stop Point

Stop after Phase 2 gate validation and report:

- Files changed.
- Tests and checks run.
- Any deferred work and the phase it belongs to.
- Any Firecrawl-sourced evidence that materially shaped implementation decisions.

Do not continue into Phase 3 without explicit user instruction.
