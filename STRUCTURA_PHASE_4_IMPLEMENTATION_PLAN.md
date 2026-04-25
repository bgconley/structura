# Structura Phase 4 Implementation Plan

Phase 4 turns parsed documents into validated, evidence-backed candidate and canonical facts. It introduces classification, typed extraction for the first three target schemas, deterministic validators, model routing, candidate/canonical promotion, review tasks, correction flows, and evidence-first UI review surfaces.

This plan expands Phase 4 from `STRUCTURA_IMPLEMENTATION_PLAN.md`. It does not replace the root plan. Use the root plan for phase boundaries and this document for Phase 4 execution detail.

## Operating Rules

- Do not inspect or rely on anything under `archive/`.
- Before coding any subphase, re-read the files listed in that subphase's **Fresh Context** section. Use `wc -l` and bounded `sed -n` chunks for large files so full reads are auditable.
- When an artifact exists in both Markdown and DOCX form, read the Markdown artifact by default. Only inspect DOCX when the user explicitly asks for layout/fidelity review or the Markdown file is missing/incomplete.
- Keep generated FastAPI OpenAPI paths aligned with `contracts/api/openapi.yaml`. If implementation and contract differ, stop and resolve the contract question explicitly.
- Preserve Phase 0-3 security posture: document, asset, job, organization, debug, review, and admin routes stay protected; browser-mutating routes require CSRF; logs and job payloads must not contain raw document text, raw model output, sensitive extracted fields, or large prompt bodies.
- Do not treat model output as accepted truth. Raw outputs, candidates, canonical facts, review decisions, and analysis notes are distinct surfaces.
- Every trusted user-visible extracted value must include a page number plus at least one concrete locator: bounding box, element ID, table row reference, text span, or source text excerpt.
- Keep Phase 4 focused on classification, extraction, validation, candidates, canonicalization, and review. Do not implement Phase 5 search/ranking, Phase 7 relationships/timelines, Phase 8 difficult-document visual retrieval, Phase 9 analysis, or Phase 10 exports except for explicit placeholders required by existing contracts.

## Firecrawl Evidence Rule

When APIs, external contracts, library behavior, security conventions, OpenAPI semantics, FastAPI/Pydantic behavior, PostgreSQL/SQL behavior, JSON Schema behavior, structured-output/model-serving behavior, Docling extraction hooks, Granite/Qwen model APIs, React/Vite conventions, Playwright behavior, or UI accessibility conventions are in play, search online with Firecrawl if there is any uncertainty.

Use primary sources where possible: official framework documentation, standards documents, official package docs, project repositories, model cards, or vendor docs. Save Firecrawl outputs under `.firecrawl/`, read them incrementally, and summarize the evidence in implementation notes or ADRs when it affects a decision. Do not use unsourced memory to settle uncertain API, schema, database, model, browser, worker, or security behavior.

## Phase 4 Required Artifact Set

The full Phase 4 artifact list from `STRUCTURA_IMPLEMENTATION_PLAN.md` remains required context:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/AGENT_START_HERE.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
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

The duplicate DOCX entries in the root plan are intentionally omitted here under the current repo guidance.

## 4.0 Baseline Reconciliation

Goal: confirm Phase 3 canonical parse is stable and identify the exact files Phase 4 will change.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 4 section.
- `STRUCTURA_PHASE_3_IMPLEMENTATION_PLAN.md`, especially Gate B and Docling/canonical debug commitments.
- `agents.md`.
- `.wolf/cerebrum.md`.
- `apps/api/structura_api/routes_documents.py`.
- `lib/jobs/service.py`.
- `lib/contracts/registry.py`.
- `workers/extraction/`.
- `compose.yaml`.
- `database/020_core_tables.sql`.
- `database/025_baseline_identity_acl_candidate_rules.sql`.
- `contracts/api/openapi.yaml`.

Work:

- Confirm Gate B is complete: Docling conversion produces persisted canonical artifacts, page/chunk rows are created, Viewer can highlight source evidence, and reprocessing supersedes state safely.
- Reconfirm current route skeletons for review tasks, review actions, field candidates, and canonical fields.
- Reconfirm table coverage for `document_extractions`, `field_candidates`, `line_item_candidates`, `canonical_fields`, `canonical_line_items`, `canonical_fact_history`, `review_tasks`, and `review_events`.
- Decide whether Phase 4 needs additive migrations for missing indexes, status constants, or review history. Prefer existing baseline objects if they cover the requirement.
- Identify model-serving mode for this implementation slice: deterministic/Docling-only fallback first, placeholder model gateway, or real local Granite/Qwen endpoints.

Firecrawl Evidence:

- If model-serving options, JSON Schema validation library behavior, Pydantic/schema generation, or current Granite/Qwen API/model-card behavior is uncertain, use Firecrawl against primary docs before deciding.

Exit Criteria:

- Phase 4 dependencies are known.
- The implementation file set is identified.
- No schema, contract, model-routing, or review API mismatch is left unresolved.

## 4.1 Document Classification

Goal: classify parsed documents into useful families and route profiles, starting with deterministic heuristics and allowing model assistance later.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `4A. Classification`.
- `pro-merged-master-v1.2/AGENT_START_HERE.md`, typed extraction rules and Gate C.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, classification requirements.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, document family classification section.
- `pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md`, routing defaults.
- `pro-merged-master-v1.2/contracts/events/classify_document_job.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/document_classification.v1.schema.json`.
- `database/020_core_tables.sql`, `documents` and `document_extractions`.
- `workers/extraction/`.

Work:

- Implement a classification service using filename, MIME, folder/tag hints, canonical text, page/table signals, existing contacts/entities where available, and parse quality metadata.
- Validate classification output against `document_classification.v1.schema.json`.
- Persist family, subtype, confidence, route profile, reasons/evidence, source engine, model trace, and review status.
- Update `documents.document_family`, `document_subtype`, and metadata in a way that preserves prior classification history.
- Support `force_reclassify` and user correction without damaging source artifacts or extraction history.
- Create review tasks for uncertain classification or high-stakes document families when policy requires review.
- Add tests for receipt, invoice, EOB, generic, low-confidence, user override, idempotent reclassification, and schema validation failure.

Firecrawl Evidence:

- Use Firecrawl if JSON Schema validation behavior, classification confidence conventions, model-assisted classification output formats, or route-profile design is uncertain.

Exit Criteria:

- Documents get useful families and route profiles.
- User corrections preserve history.
- Classification output is schema-validated and reviewable.

## 4.2 Extraction Schema Registry And Validators

Goal: implement strict schema validation and deterministic validation for receipt, invoice, and medical EOB outputs.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `4B. Extraction Validators`.
- `pro-merged-master-v1.2/contracts/schemas/receipt.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/invoice.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/medical_eob.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/common_defs.schema.json`.
- `pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md`, validation contract.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, Epic 4 and Epic 5.
- `lib/contracts/registry.py`.
- `tests/`.

Work:

- Add a schema registry for extraction schemas and versions.
- Add Pydantic or JSON-Schema validation wrappers for receipt, invoice, and medical EOB.
- Add deterministic checks: missing required fields, money shape/currency checks, receipt subtotal/tax/tip/discount/total arithmetic, invoice due date not before issue date, invoice balance consistency, and EOB service-line/summary plausibility.
- Add evidence adequacy checks: trusted fields require page number plus one stronger locator.
- Produce structured validation output with machine-readable check IDs, severity, field paths, messages, and `needs_review`.
- Add tests for valid schemas, malformed payloads, arithmetic mismatch, missing required fields, date inconsistency, weak evidence, and structured validation output.

Firecrawl Evidence:

- Use Firecrawl if JSON Schema draft 2020-12 validation, Pydantic compatibility, money rounding, date parsing, or deterministic validation conventions are uncertain.

Exit Criteria:

- Invalid extraction cannot become an accepted canonical fact.
- Validation output is structured.
- Gate C arithmetic and missing-required-field checks exist.

## 4.3 Evidence Resolver And Source Locator Contract

Goal: connect extracted values to concrete source locators from canonical parse data.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 4 gate.
- `pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md`, evidence contract.
- `pro-merged-master-v1.2/docs/14_Canonicalization_Candidate_Authority_Model.md`, automatic promotion criteria and review triggers.
- `pro-merged-master-v1.2/contracts/schemas/common_defs.schema.json`, `evidenceRef`.
- `database/020_core_tables.sql`, `document_pages`, `document_elements`, `document_tables`, `document_chunks`.
- `STRUCTURA_PHASE_3_IMPLEMENTATION_PLAN.md`, canonical-to-relational population commitments.

Work:

- Implement evidence normalization from model/Docling output into canonical `evidenceRef` shape.
- Resolve candidate evidence to pages, bounding boxes, element IDs, table IDs/rows, text spans, or source text excerpts.
- Reject or downgrade trusted promotion when evidence is page-only or missing.
- Add server-side helpers for UI evidence jumps: field path to page/element/table/text span.
- Add tests for bbox evidence, element evidence, table row evidence, text-span evidence, source-text evidence, page-only rejection for trusted fields, and missing-page behavior.

Firecrawl Evidence:

- Use Firecrawl if Docling provenance fields, coordinate systems, bbox normalization, PDF/image coordinate conventions, or text span conventions are uncertain.

Exit Criteria:

- Trusted extracted values have concrete evidence.
- Evidence jump data is available to the Viewer and review UI.

## 4.4 Model Gateway And Routing Abstraction

Goal: add a model gateway abstraction that can route extraction work without hard-coding one model path into business logic.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `4C. Model Routing And Extraction Workers`.
- `pro-merged-master-v1.2/docs/10_Architectural_Decision_Record_Summary.md`, ADR-012 and authority/routing additions.
- `pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md`, routing defaults and output requirements.
- `pro-merged-master-v1.2/docs/14_Canonicalization_Candidate_Authority_Model.md`, authority matrix.
- `pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv`.
- `compose.yaml`, model placeholders and worker profiles.
- `workers/model_placeholder.py`.
- `workers/extraction/`.

Work:

- Define a model gateway interface for Docling-derived extraction, Granite extraction, Qwen extraction/arbitration, and validator-only paths.
- Keep the initial implementation compatible with local placeholder services and deterministic/fixture-based extraction tests.
- Route by document family, parse quality, table density, handwriting suspicion, and configured route profile.
- Persist model name, model version, prompt version, schema version, and route profile for every extraction run.
- Add timeout, retry, failure classification, and safe raw-output handling.
- Add tests for routing decisions, placeholder gateway behavior, model metadata persistence, timeout/failure handling, and no raw text in job payloads/logs.

Firecrawl Evidence:

- Use Firecrawl to verify current Granite/Qwen model cards, vLLM or transformers structured-output behavior, HTTP API conventions, and any official structured decoding guidance before implementing real gateway adapters.

Exit Criteria:

- Extraction orchestration is decoupled from a single model implementation.
- Docling-only, Granite, Qwen, and validator roles are explicit.

## 4.5 Extraction Workers And Raw/Normalized Output Persistence

Goal: run extraction jobs and persist raw outputs, normalized outputs, and extraction run state.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `4C. Model Routing And Extraction Workers`.
- `pro-merged-master-v1.2/contracts/events/extract_document_job.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/receipt.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/invoice.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/medical_eob.v1.schema.json`.
- `database/010_types_and_enums.sql`, `asset_role_enum`, `model_source_enum`, and extraction status enums.
- `database/020_core_tables.sql`, `document_extractions`, `document_fields`, `document_line_items`, and `document_assets`.
- `lib/jobs/service.py`.
- `workers/extraction/`.

Work:

- Consume `extract_document` jobs for target schemas `receipt`, `invoice`, and `medical_eob`.
- Use canonical parse rows/artifacts from Phase 3 as the input substrate.
- Persist raw model output as a `raw_model_output` derived asset when a model path is used.
- Persist normalized extraction JSON and validation JSON in `document_extractions`.
- Mark one extraction run current per document/schema while preserving historical runs.
- Optionally populate legacy projection tables `document_fields` and `document_line_items` for compatibility, while treating candidate/canonical tables as the authority surfaces.
- Add tests for successful extraction run, failed extraction run, current-run superseding, raw asset persistence, normalized JSON validation, and job retry/dead-letter behavior.

Firecrawl Evidence:

- Use Firecrawl if worker serialization, structured-output parsing, raw output retention, schema versioning, or model gateway response behavior is uncertain.

Exit Criteria:

- Receipt, invoice, and EOB extraction run end-to-end on real or controlled samples.
- Raw and normalized outputs are both retained.

## 4.6 Candidate Normalization

Goal: normalize extraction outputs into field and line-item candidates without prematurely accepting them.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `4C. Model Routing And Extraction Workers`.
- `pro-merged-master-v1.2/docs/14_Canonicalization_Candidate_Authority_Model.md`, candidate definitions and field path convention.
- `pro-merged-master-v1.2/contracts/schemas/field_candidate.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/canonical_field.v1.schema.json`.
- `database/025_baseline_identity_acl_candidate_rules.sql`, `field_candidates` and `line_item_candidates`.
- `contracts/api/openapi.yaml`, `FieldCandidate`.

Work:

- Map normalized extraction JSON to stable dotted field paths.
- Convert scalar values into `field_candidates` with typed value columns, normalized values, currency, source engine, authority weight, evidence, validation, and status.
- Convert line items into `line_item_candidates`, preserving candidate groups and table/row evidence.
- Preserve competing candidates from different engines rather than overwriting them.
- Mark candidate status based on validation: proposed, needs_review, rejected, promoted, or superseded.
- Add tests for receipt fields/line items, invoice fields/line items, EOB service lines, money/date normalization, competing candidate sets, weak evidence status, and idempotent rerun.

Firecrawl Evidence:

- Use Firecrawl if field path conventions, JSON-to-relational mapping, money/date normalization, or candidate grouping design is uncertain.

Exit Criteria:

- Candidate facts are inspectable.
- Candidate rows retain source, confidence, authority, validation, and evidence.

## 4.7 Canonical Promotion And Authority Matrix

Goal: promote candidates into canonical fields and canonical line items only when policy allows.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `4D. Canonical Promotion`.
- `pro-merged-master-v1.2/docs/13_Golden_Master_Review_and_Merge_Plan.md`, authority model integration.
- `pro-merged-master-v1.2/docs/14_Canonicalization_Candidate_Authority_Model.md`, canonicalization order and automatic promotion criteria.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`, canonical facts as default read model.
- `database/025_baseline_identity_acl_candidate_rules.sql`, `canonical_fields`, `canonical_line_items`, and `canonical_fact_history`.
- `contracts/api/openapi.yaml`, `CanonicalField` and `CanonicalFieldWrite`.

Work:

- Implement an authority matrix:
  - Docling: structure and grounding.
  - Granite: tables, KVPs, line items.
  - Qwen: classification, OCR rescue, handwriting, arbitration.
  - Validators: deterministic promotion/rejection.
  - Human: final override.
- Implement automatic promotion only when evidence, schema validation, deterministic validation, confidence, policy, and conflict checks allow it.
- Create review tasks when candidates conflict, evidence is weak, required fields are missing, validation fails, confidence is low, or document sensitivity policy requires review.
- Persist canonical facts and canonical fact history for auto-promotion, human edits, rejections, and superseding changes.
- Ensure UI/document detail reads accepted facts from `canonical_fields` and `canonical_line_items`.
- Add tests for auto-promotion success, weak-evidence rejection, validation failure, conflict review task, human override, history preservation, and rerun superseding.

Firecrawl Evidence:

- Use Firecrawl if deterministic reconciliation policies, audit/history patterns, or OpenAPI/Pydantic representations for typed values are uncertain.

Exit Criteria:

- UI reads accepted facts from canonical tables.
- Candidate conflicts are visible in review surfaces.
- Human corrections do not erase candidates/history.

## 4.8 Review Task Generation And Review Actions API

Goal: make uncertain extraction a managed workflow with auditable user decisions.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `4E. Review Queue And Evidence Inspector`.
- `pro-merged-master-v1.2/contracts/schemas/review_action.v1.schema.json`.
- `contracts/api/openapi.yaml`, `/api/v1/review-tasks`, `/api/v1/documents/{documentId}/review-actions`, `/field-candidates`, and `/canonical-fields`.
- `database/020_core_tables.sql`, `review_tasks` and `review_events`.
- `database/025_baseline_identity_acl_candidate_rules.sql`, `canonical_fact_history`.
- `apps/api/structura_api/routes_documents.py`.

Work:

- Implement review task creation for low confidence, arithmetic mismatch, missing required fields, uncertain classification, weak evidence, candidate conflicts, handwriting-heavy documents, and explicit user requests.
- Implement `GET /api/v1/review-tasks` with status/limit filters and household/document authorization.
- Implement review actions: accept field, reject field, correct field, reclassify document, mark reviewed, and re-run extraction.
- Implement `GET /field-candidates`, `GET /canonical-fields`, and `POST /canonical-fields` using contract casing and authorization.
- Record `review_events` and canonical history for every user-visible correction.
- Add tests for task generation, list filtering, accept/reject/correct/reclassify actions, CSRF protection, authorization, audit rows, and re-extraction job creation.

Firecrawl Evidence:

- Use Firecrawl if REST semantics, CSRF behavior, audit event patterns, or review workflow conventions are uncertain.

Exit Criteria:

- User can resolve uncertain fields.
- Corrections are auditable.
- Review APIs match the contract.

## 4.9 Review Queue And Evidence Inspector UI

Goal: implement the second UI priority slice for extraction/review surfaces.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `4E. Review Queue And Evidence Inspector`.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`.
- `pro-merged-master-v1.2/design-language-v1.3.html`.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`, evidence inspector, status chips, and interaction principles.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, review workflow expectations.
- `contracts/api/openapi.yaml`, review/candidate/canonical schemas.
- `apps/web/src/App.tsx`.
- `apps/web/src/styles.css`.

Work:

- Add a review queue surface listing review tasks by priority, reason, family, field path, status, and document context.
- Add candidate comparison panel showing canonical value, candidates, confidence, source engine, validation checks, evidence, and history.
- Add evidence jump/highlight from field/candidate to Viewer page, bbox/element/table/text span where available.
- Add actions: accept, reject, edit/correct, mark reviewed, re-run extraction, and reclassify.
- Keep review state visible in Inbox/Viewer/inspector without letting debug/model details dominate the workbench.
- Add Playwright tests for review queue, candidate comparison, evidence jump, field correction, mark reviewed, re-run extraction, and responsive layout.

Firecrawl Evidence:

- Use Firecrawl for uncertain React state/routing, WAI-ARIA table/tabs/dialog patterns, canvas/PDF highlight behavior, or Playwright locator conventions.

Exit Criteria:

- User can resolve uncertain fields from the UI.
- Evidence jump is one click away.
- The UI presents suggested/unresolved/review-required states honestly.

## 4.10 Golden Samples, Evaluation Hooks, And Regression Fixtures

Goal: add enough fixture discipline to prevent false confidence in extraction quality.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 4 gate.
- `pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md`, false trust and Phase 4 review cadence.
- `pro-merged-master-v1.2/docs/13_Golden_Master_Review_and_Merge_Plan.md`, operational launch bar and evaluation readiness.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, benchmark/evaluation notes.
- `tests/`.

Work:

- Add lightweight golden fixtures for receipt, invoice, and EOB extraction where licensing/privacy allows.
- Store expected classification, key fields, line items, validation outcomes, evidence adequacy, and review-task expectations.
- Add regression tests for deterministic validators and candidate/canonical promotion logic.
- Add extraction metrics hooks where useful: field present/absent, exact match, numeric tolerance, evidence present, validation pass/fail.
- Clearly separate test fixtures from real private documents.

Firecrawl Evidence:

- Use Firecrawl if synthetic PDF generation, benchmark metric conventions, or JSON fixture validation approaches are uncertain.

Exit Criteria:

- Three target schemas have repeatable regression coverage.
- Extraction quality failures are visible before retrieval/search depends on accepted facts.

## 4.11 Integration, Reprocessing, And Safety Coverage

Goal: prove the typed extraction workflow works end to end, including reruns and user corrections.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 4 gate.
- `pro-merged-master-v1.2/AGENT_START_HERE.md`, Gate C.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, Epic 4 and Epic 5.
- `pro-merged-master-v1.2/docs/14_Canonicalization_Candidate_Authority_Model.md`.
- `contracts/events/classify_document_job.v1.schema.json`.
- `contracts/events/extract_document_job.v1.schema.json`.
- `tests/`.

Work:

- Add integration tests from parsed document fixture to classification to extraction to validation to candidates to canonical promotion/review task.
- Add reprocessing tests: re-run classification/extraction, supersede current runs safely, preserve raw outputs, candidates, canonical history, and human corrections.
- Add security tests: no raw text/model output in job payloads/logs, review routes require auth/CSRF where appropriate, cross-household access denied, no object URI leaks.
- Add no-model fallback tests for deterministic/fixture path where real model services are disabled.
- Add failure tests for model timeout, invalid model output, schema validation failure, weak evidence, arithmetic mismatch, and dead-letter behavior.

Firecrawl Evidence:

- Use Firecrawl if test harness behavior, model timeout simulation, JSON Schema validation, or reprocessing/audit conventions need confirmation.

Exit Criteria:

- Receipt, invoice, and EOB extraction workflows are end-to-end.
- Review tasks are automatic.
- Reprocessing is idempotent and history-preserving.

## 4.12 Contract, Static Analysis, Runtime, UI, And Gate C

Goal: prove Phase 4 is stable before retrieval is treated as product-ready.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 4 gate.
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
- Run extraction worker tests and schema validator tests.
- Run web build.
- Run Playwright UI workflow and screenshot validation for review queue, evidence inspector, candidate comparison, and correction flows.
- Run local Compose smoke where practical: API health, worker health, upload/list/detail from Phase 1, filing from Phase 2, parse/debug from Phase 3, classification, extraction, review task list, candidate/canonical field APIs, and review actions.
- Confirm Gate C from `AGENT_START_HERE.md`: receipt, invoice, and EOB schemas validate; arithmetic and missing-required checks exist; review tasks are generated automatically; manual corrections are persisted and auditable.
- Document intentional deferrals: search/ranking, embeddings, relationship matching, difficult visual retrieval beyond routing/escalation, analysis workspace, exports, broad golden corpus scoring, and production model optimization.

Firecrawl Evidence:

- If a gate fails due to tool behavior, dependency behavior, model behavior, structured output behavior, browser/API semantics, SQL behavior, JSON Schema behavior, or security convention that is not locally obvious, use Firecrawl to find primary-source evidence before changing code.

Exit Criteria:

- Three target schemas work.
- Evidence is concrete.
- Review tasks are automatic.
- Human corrections do not erase candidates/history.
- Gate C passes before Phase 5 search/retrieval is treated as product-ready.

## Stop Point

Stop after Phase 4 gate validation and report:

- Files changed.
- Tests and checks run.
- Any deferred work and the phase it belongs to.
- Any Firecrawl-sourced evidence that materially shaped implementation decisions.

Do not continue into Phase 5 without explicit user instruction.
