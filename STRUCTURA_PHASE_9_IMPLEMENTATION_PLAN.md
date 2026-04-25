# Structura Phase 9 Implementation Plan

Phase 9 adds the optional analysis workspace after the filing, extraction, review, search, relationship, and difficult-document foundations are strong. Analysis is useful only if it is bounded, citation-backed, disabled without breaking core workflows, and clearly separate from canonical accepted facts.

This plan expands Phase 9 from `STRUCTURA_IMPLEMENTATION_PLAN.md`. It does not replace the root plan. Use the root plan for phase boundaries and this document for Phase 9 execution detail.

## Operating Rules

- Do not inspect or rely on anything under `archive/`.
- Before coding any subphase, re-read the files listed in that subphase's **Fresh Context** section. Use `wc -l` and bounded `sed -n` chunks for large files so full reads are auditable.
- When an artifact exists in both Markdown and DOCX form, read the Markdown artifact by default. Only inspect DOCX when the user explicitly asks for layout/fidelity review or the Markdown file is missing/incomplete.
- Keep generated FastAPI OpenAPI paths aligned with `contracts/api/openapi.yaml`. If implementation and contract differ, stop and resolve the contract question explicitly.
- Preserve Phase 1-8 invariants: original bytes are immutable, canonical facts remain the default read model, candidates and model outputs remain reviewable, search indexes are assistive, relationship suggestions remain distinct from confirmed relationships, visual/handwriting uncertainty is explicit, browser-mutating routes require CSRF, and access control is enforced before returning document-derived content.
- Analysis is opt-in. The app must stay useful when analysis is disabled, when the analysis worker is offline, or when `model-qwen` is unavailable.
- Analysis notes are persisted separately from extraction, canonical facts, relationships, folders, tags, deadlines, and exports. They must never silently mutate accepted data.
- Every analysis answer must cite source documents and pages. Do not present uncited model assertions as trusted analysis.
- Do not log raw document text, model prompts, model responses, analysis answers, citations excerpts, object-storage paths, or presigned asset URLs.
- Keep Phase 9 focused on analysis runs, analysis-note persistence, cited outputs, recommended-action suggestions, the Figma analysis workspace, validation, and Gate E. Do not implement Phase 10 exports, backup hardening, redaction bundles, or release operations except for contract-safe placeholders already present.

## Firecrawl Evidence Rule

When APIs, external contracts, library behavior, security conventions, OpenAPI semantics, FastAPI/Pydantic behavior, PostgreSQL JSON/transaction behavior, job queue semantics, model-serving APIs, Qwen/vLLM structured output behavior, local inference configuration, prompt/schema versioning, citation validation methods, medical/tax/legal safety conventions, React/Vite behavior, Figma MCP behavior, Playwright behavior, or accessibility conventions are in play, search online with Firecrawl if there is any uncertainty.

Use primary sources where possible: official framework documentation, standards documents, official package docs, project repositories, security guidance, model cards, or vendor docs. Save Firecrawl outputs under `.firecrawl/`, read them incrementally, and summarize the evidence in implementation notes or ADRs when it affects a decision. Do not use unsourced memory to settle uncertain API, schema, database, model, prompt, browser, worker, or security behavior.

## Phase 9 Required Artifact Set

The full Phase 9 artifact list from `STRUCTURA_IMPLEMENTATION_PLAN.md` remains required context:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/AGENT_START_HERE.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
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

The duplicate DOCX entries in the root plan are intentionally omitted here under the current repo guidance.

## 9.0 Baseline Reconciliation And Gate E Readiness

Goal: confirm the product is ready for analysis and that Phase 9 will not hide gaps in ingestion, extraction, review, search, relationships, or difficult-document handling.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 9 section.
- `AGENT_START_HERE.md`, non-negotiable rules, third implementation milestone, and Gate E.
- `STRUCTURA_PHASE_4_IMPLEMENTATION_PLAN.md`, extraction, canonical facts, review, and evidence commitments.
- `STRUCTURA_PHASE_5_IMPLEMENTATION_PLAN.md`, search, retrieval context, hybrid ranking, and benchmark commitments.
- `STRUCTURA_PHASE_7_IMPLEMENTATION_PLAN.md`, related documents and timeline commitments.
- `STRUCTURA_PHASE_8_IMPLEMENTATION_PLAN.md`, visual retrieval and difficult-document uncertainty commitments.
- `agents.md`.
- `.wolf/cerebrum.md`.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, optional analysis workspace.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, optional analysis workspace.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, privacy, audit, and AI output requirements.
- `pro-merged-master-v1.2/docs/10_Architectural_Decision_Record_Summary.md`, ADR-009 and ADR-012.
- Active `contracts/api/openapi.yaml`.
- Active `database/020_core_tables.sql`.
- `compose.yaml`.
- `workers/analysis/`.

Work:

- Confirm Gate D retrieval baseline and Phase 8 difficult-document gate are implemented or explicitly accepted as prerequisites before user-facing analysis is enabled.
- Confirm structured viewing of receipt, invoice, and EOB extractions, manual correction flows, related-document navigation, and search are strong enough that analysis is additive rather than a workaround.
- Inventory the active Phase 9 baseline: `analysis_notes` table, `job_type = analyze`, `POST /api/v1/analysis-notes`, `analyze_documents_job.v1`, `analysis_note.v1`, `worker-analysis`, and `model-qwen`.
- Decide whether Phase 9 needs only the existing POST route plus job lookup, or whether additional analysis-note read/list/delete routes are required. Any public API extension must update OpenAPI and route parity tests in the same change.
- Define the default feature flag behavior: analysis disabled or unavailable must show a clear UI state and must not block ingest, browse, filing, review, search, relationships, exports, or admin health.
- Record implementation assumptions for note editability. The artifact risk register asks whether notes should be editable; prefer immutable generated notes plus future user annotations unless the user decides otherwise.

Firecrawl Evidence:

- Use Firecrawl if Gate E interpretation, OpenAPI extension strategy, local model-serving expectations, or generated-note immutability conventions are uncertain.

Exit Criteria:

- Phase 9 prerequisites are verified.
- Contract gaps are identified before implementation.
- Analysis remains optional and separate from canonical product behavior.

## 9.1 Analysis Contracts, DTOs, And Persistence Model

Goal: make analysis request, job, result, citation, model-trace, and persistence shapes explicit before worker or UI implementation.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 9 task list.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, `/api/v1/analysis-notes`.
- `pro-merged-master-v1.2/contracts/events/analyze_documents_job.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/analysis_note.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/common_defs.schema.json`, citation and evidence definitions.
- `pro-merged-master-v1.2/database/020_core_tables.sql`, `analysis_notes`, `pipeline_jobs`, `audit_events`, document tables, and canonical fact tables.
- `database/010_types_and_enums.sql`, `analysis_note_type_enum` and `job_type_enum`.
- `lib/contracts/registry.py`.
- `apps/api/structura_api/routes_documents.py`, current Phase 9 placeholder.

Work:

- Define backend DTOs for `AnalysisRequest`, `AnalysisJobAccepted`, `AnalysisNote`, `AnalysisCitation`, `RecommendedAction`, and `ModelTrace` using the active OpenAPI and JSON Schema contracts.
- Validate allowed note types: `summary`, `explanation`, `comparison`, `timeline`, `obligation_scan`, `tax_scan`, and `medical_explanation`.
- Reconcile naming between OpenAPI camelCase (`analysisNoteType`, `documentIds`, `saveResult`) and event/schema/database snake_case fields.
- Decide how completed analysis notes are retrieved. Prefer returning the persisted note id in job `result_json` and using existing job status until a documented note-list/detail route is added.
- Confirm `analysis_notes` can store selected document scope, answer markdown, structured answer JSON, citations, recommended actions, model name/version, prompt version, and prompt/question. Add a scoped migration if created-by, household, status, or immutable-note metadata is required for ACL/audit.
- Add validation tests for schema parity, DTO serialization, enum handling, required citations, recommended action shapes, malformed requests, and database persistence.

Firecrawl Evidence:

- Use Firecrawl if OpenAPI/Pydantic alias handling, JSON Schema draft behavior, PostgreSQL JSONB persistence, or immutable note modeling is uncertain.

Exit Criteria:

- Analysis DTOs are contract-aligned.
- The persistence model can represent the Phase 9 outputs without confusing them with canonical facts.
- Contract parity tests cover analysis request and result shapes.

## 9.2 Document Scope, ACL, Sensitivity, And Citation Policy

Goal: ensure analysis can only use documents the requester is allowed to see and that every citation is safe to return.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 9 gate.
- `AGENT_START_HERE.md`, provenance and local-first rules.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, access, privacy, audit, and analysis output requirements.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, sensitive-data posture and optional analysis workspace.
- `pro-merged-master-v1.2/database/020_core_tables.sql`, documents, pages, chunks, assets, analysis notes, and audit events.
- `pro-merged-master-v1.2/contracts/schemas/common_defs.schema.json`, citation shape.
- Phase 1 asset authorization implementation.
- Phase 2 folder/ACL implementation.
- Phase 5 search ACL and filtering implementation.

Work:

- Implement a document-scope resolver that validates all selected document ids, preserves requested order, rejects duplicates as needed, and confirms the requester can access each document.
- Apply sensitivity policy before context building. Highly sensitive documents may require an explicit request flag, UI warning, or complete refusal depending on current product policy.
- Ensure analysis responses, job results, citations, excerpts, and recommended actions never reveal hidden documents through titles, snippets, counts, page ids, or failure messages.
- Define citation requirements: every substantive claim should have at least one source citation; citations must reference a selected document and existing page; element/table ids must exist when provided.
- Define excerpt policy: include short, useful excerpts only when they come from authorized document text and are needed for source verification.
- Audit analysis note saves and optionally analysis requests, but do not log raw prompt context or answer content.
- Add tests for cross-household denial, hidden document suppression, sensitivity gating, unauthorized citation rejection, stale page id rejection, excerpt redaction, and audit event creation.

Firecrawl Evidence:

- Use Firecrawl if security guidance, privacy redaction patterns, citation verification methods, or framework authorization behavior is uncertain.

Exit Criteria:

- Analysis scope is authorized before any context is built.
- Citations cannot point outside the selected authorized document set.
- Sensitive documents receive explicit policy handling.

## 9.3 Analysis Request API And Job Enqueue

Goal: implement `POST /api/v1/analysis-notes` as an authenticated, CSRF-safe job-start endpoint.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `POST /api/v1/analysis-notes` task.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, analysis POST request and `AcceptedJob` response.
- `pro-merged-master-v1.2/contracts/events/analyze_documents_job.v1.schema.json`.
- `contracts/events/README.md`.
- `apps/api/structura_api/routes_documents.py`, current placeholder.
- `lib/jobs/service.py`.
- Phase 0 auth/session and CSRF implementation.
- Phase 9 document scope resolver from subphase 9.2.

Work:

- Replace the placeholder with a real endpoint that accepts the documented request body and returns `202` with `AcceptedJob`.
- Require authentication for all analysis requests. Require CSRF for browser cookie-auth mutations; preserve token-only automation behavior if the active auth dependency distinguishes it.
- Validate `analysisNoteType`, `documentIds`, `question`, and `saveResult`.
- Reject requests when analysis is disabled, no selected document is accessible, selected documents are in an unusable state, or requested note type is incompatible with the document set.
- Create a durable `pipeline_jobs` row with `job_type = analyze` and payload matching `analyze_documents_job.v1.schema.json`.
- Include correlation id, prompt version, requested_by, save_result, include_citations, and sanitized metadata in the job payload.
- Add tests for happy path, CSRF, API-token path, disabled analysis, invalid note type, empty document ids, unauthorized documents, sensitivity policy, event schema validation, and job payload correctness.

Firecrawl Evidence:

- Use Firecrawl if FastAPI request validation, CSRF conventions, OpenAPI status semantics, or job enqueue transaction behavior is uncertain.

Exit Criteria:

- Analysis requests enqueue valid jobs.
- API behavior matches OpenAPI exactly.
- Disabled or unauthorized requests fail cleanly without leaking content.

## 9.4 Retrieval And Context Package Builder

Goal: construct bounded, source-linked context packages from selected documents for analysis workers.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, analysis scope and citation tasks.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, optional analysis types.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, core analysis actions.
- `pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md`, long legal/reference PDF and Qwen analysis notes.
- Phase 3 canonical parse, pages, chunks, and evidence implementation.
- Phase 4 canonical fact and review implementation.
- Phase 5 search/retrieval implementation.
- Phase 7 relationship/timeline implementation.
- Phase 8 difficult-document uncertainty implementation.

Work:

- Build an analysis context service that can gather selected document metadata, canonical facts, reviewed corrections, page text, chunks, relationships, deadlines, and relevant search hits.
- Prefer accepted canonical facts for factual summaries. Candidate facts and unreviewed handwriting/visual outputs may be included only with uncertainty labels.
- Keep context bounded by token, page, document, and byte limits. Refuse or ask for narrower scope when selected documents exceed safe context limits.
- For each context item, retain source locators that can become citations: document id, page number, element id, table id, row index, source text span, or excerpt.
- Select context differently by note type: comparison needs aligned documents; timeline needs dated facts and related documents; obligation scan needs deadlines and action language; tax scan needs categorized expenses; medical explanation needs EOB/service-line facts.
- Exclude raw model output and debug-only artifacts unless explicitly needed and safe.
- Add tests for context building by note type, context limits, reviewed-vs-unreviewed handling, citation locator retention, long document selection, visual/handwriting uncertainty, and no unauthorized content.

Firecrawl Evidence:

- Use Firecrawl if RAG context packaging patterns, token budgeting, citation chunking, or source-attribution methods are uncertain.

Exit Criteria:

- Workers receive bounded, traceable context packages.
- Every context item can map back to a source citation.
- Unreviewed uncertainty remains visible to the analysis layer.

## 9.5 Prompt Versions, Model Gateway, And Output Validation

Goal: define prompt contracts and validate model output before persistence.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, supported analysis types.
- `pro-merged-master-v1.2/docs/10_Architectural_Decision_Record_Summary.md`, model-output versioning and analysis separation ADRs.
- `pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md`, Qwen analysis and structured output guidance.
- `pro-merged-master-v1.2/contracts/schemas/analysis_note.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/common_defs.schema.json`.
- `pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv`, `worker-analysis` and `model-qwen`.
- Active model gateway/configuration from Phase 4.

Work:

- Create checked-in prompt templates or prompt builders for each analysis type: summary, explanation, comparison, timeline, obligation scan, tax scan, and medical explanation.
- Version every prompt. Persist prompt version, model name, model version, model profile, structured output schema version, and generation settings.
- Instruct the model to produce source-cited, bounded output, with a clear distinction between document facts, analysis, uncertainty, and suggested next actions.
- Use structured output where the serving stack supports it. Always run post-hoc validation against `analysis_note.v1` or equivalent DTOs.
- For tax, legal, and medical outputs, keep language explanatory and source-grounded. Do not present professional advice, diagnosis, or legal conclusions as authoritative.
- Treat missing citations, citations outside scope, hallucinated pages, malformed recommended actions, and empty answers as validation failures.
- Add tests for prompt version registration, schema validation, missing citations, invalid citations, unsupported note type, model unavailable, malformed JSON, and safe handling of medical/tax/legal note types.

Firecrawl Evidence:

- Use Firecrawl if Qwen/vLLM structured output APIs, JSON schema constrained decoding, model card behavior, or professional-advice safety conventions are uncertain.

Exit Criteria:

- Prompt versions and model metadata are persistent and inspectable.
- Invalid or uncited model output is rejected or marked failed.
- Analysis language stays bounded and source-grounded.

## 9.6 Worker-Analysis Execution Path

Goal: process analysis jobs asynchronously with retry-safe, observable behavior.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, analysis run model task.
- `pro-merged-master-v1.2/contracts/events/analyze_documents_job.v1.schema.json`.
- `pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv`, `worker-analysis`.
- `compose.yaml`, `worker-analysis`, `model-qwen`, and analysis profile.
- `workers/analysis/`.
- `workers/placeholder.py`.
- `lib/jobs/service.py`.
- Phase 4 worker/model gateway patterns.
- Phase 5 job and benchmark patterns.

Work:

- Replace or extend the `worker-analysis` placeholder with a real worker that claims `analyze` jobs.
- Validate the job payload against `analyze_documents_job.v1` before work begins.
- Resolve requester/scope policy, build the analysis context package, invoke the model gateway, validate output, and persist or discard result according to `save_result`.
- Update job state through leased/running/succeeded/failed/dead-letter transitions with bounded retries.
- Store the created analysis note id and safe summary metadata in `pipeline_jobs.result_json`.
- Preserve idempotency: retrying the same job should not create duplicate saved notes unless the prior attempt failed before persistence.
- Add health and service snapshot behavior for worker available, model unavailable, disabled analysis, validation failure, and dead-letter conditions.
- Add tests for claim/complete/fail, payload validation, idempotent retry, `save_result = false`, model timeout, invalid output, disabled feature flag, and redacted logs.

Firecrawl Evidence:

- Use Firecrawl if worker lease semantics, vLLM timeout behavior, model gateway streaming behavior, or background-job idempotency patterns are uncertain.

Exit Criteria:

- Analysis jobs run asynchronously and safely retry.
- Completed jobs expose a safe result reference.
- Worker failures are visible without leaking private content.

## 9.7 Analysis Note Persistence, Citations, And Recommended Actions

Goal: persist analysis output as a separate, auditable artifact with validated citations and non-mutating action suggestions.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, persistence and separation tasks.
- `pro-merged-master-v1.2/contracts/schemas/analysis_note.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/common_defs.schema.json`, citation definition.
- `pro-merged-master-v1.2/database/020_core_tables.sql`, `analysis_notes`, `audit_events`, `review_tasks`, `document_deadlines`, and relationships.
- `pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md`, editability open question.
- Phase 4 review/canonical promotion implementation.
- Phase 7 deadline and relationship implementation.

Work:

- Persist generated notes into `analysis_notes` with note type, title, user prompt, model metadata, prompt version, answer markdown, answer JSON, citations JSON, document scope JSON, and created timestamp.
- Validate every citation before persistence. A note with no valid citations should fail unless the note type is explicitly allowed to be empty, which Phase 9 should avoid.
- Validate recommended actions as suggestions only: `review_field`, `review_relationship`, `add_deadline`, `reclassify_document`, `move_folder`, `add_tag`, or `none`.
- Do not apply recommended actions automatically. If UI later offers apply buttons, those buttons must call the existing explicit review, relationship, deadline, folder, or tag flows with authorization, CSRF, and audit.
- Decide whether generated notes are immutable. Prefer immutable generated notes plus explicit deletion/archive or future user annotations.
- Add audit events for saved notes and for any later explicit action taken from a recommendation.
- Add tests for persistence, citation validation, invalid recommended action rejection, no mutation of canonical fields, no automatic deadline creation, no relationship creation, audit event creation, and immutable-note behavior.

Firecrawl Evidence:

- Use Firecrawl if citation storage patterns, audit event modeling, immutable generated artifact conventions, or recommended-action UX/security patterns are uncertain.

Exit Criteria:

- Analysis notes are saved separately and auditably.
- Citations are valid and page-linked.
- Recommended actions cannot mutate product state silently.

## 9.8 Analysis Workspace UI And Figma Frame 14:990

Goal: implement the user-facing analysis workspace from Figma without turning the product into a generic chat shell.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Figma frame `14:990` task.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`, Figma MCP workflow, analysis slice rules, Playwright rules, and UI stop rule.
- `pro-merged-master-v1.2/design-language-v1.3.html`, calm evidence workbench baseline.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, optional analysis workspace.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, Epic 8 analysis stories.
- Active web app shell, navigation, search, viewer, review, and relationship UI.
- Active `POST /api/v1/analysis-notes` implementation.

Work:

- Use Figma MCP to inspect concrete frame `14:990`, component variants `35:2`, interaction specs `35:7`, edge states `35:12`, and dev redlines `35:17`.
- Save Figma context, reference screenshot, Playwright screenshot, and comparison notes under `docs/ui-reference/figma/analysis-workspace/`.
- Implement document selection, note type selection, question input, run button, disabled/unavailable state, running state, failed state, result view, citation list, source jump, recommended actions, and save-result behavior exactly as the Figma/artifact contract allows.
- Keep analysis in its own workspace and navigation entry. Do not make chat the default filing, search, or review interface.
- Citation clicks must open the source document/page and highlight source evidence where locator data exists.
- Show clear separation between extracted facts, analysis text, uncertainty, and recommended actions.
- Ensure no raw object storage path, raw model trace, prompt context, or unauthorized excerpt appears in the DOM or API payloads.
- Add Playwright checks for disabled state, create analysis request, job accepted, running state, completed saved note, citation jump, validation failure, no selected documents, multi-document comparison, and responsive behavior.

Firecrawl Evidence:

- Use Firecrawl if Figma MCP behavior, React/Vite conventions, ARIA patterns, Playwright screenshot comparison, keyboard focus behavior, or browser security behavior is uncertain.

Exit Criteria:

- Frame `14:990` is implemented with documented visual comparison.
- Analysis UX remains bounded, citation-first, and separate from canonical facts.
- UI workflow tests cover key states.

## 9.9 Core Analysis Actions

Goal: support the required analysis note types with type-specific context and validation.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, supported analysis action list.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, analysis action list.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, Subphase 7B.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, medical explanation and comparison stories.
- `pro-merged-master-v1.2/contracts/events/analyze_documents_job.v1.schema.json`.
- `pro-merged-master-v1.2/contracts/schemas/analysis_note.v1.schema.json`.
- Phase 5 search context.
- Phase 7 timeline/deadline/relationship context.
- Phase 8 difficult-document context.

Work:

- Implement type-specific handlers for:
  - `summary`: concise document-set summary with cited pages.
  - `explanation`: plain-language explanation of a selected document or group.
  - `comparison`: cited differences and similarities across multiple selected documents.
  - `timeline`: cited sequence of events using document dates, deadlines, relationships, and source pages.
  - `obligation_scan`: potential obligations, deadlines, due dates, or action items as suggestions.
  - `tax_scan`: tax-relevant expense or record suggestions, clearly non-authoritative.
  - `medical_explanation`: plain-language EOB/bill explanation, clearly non-diagnostic and source-grounded.
- Enforce note-type input constraints, such as requiring at least two documents for comparison unless the product explicitly allows comparing sections within one document.
- Tailor context selection and validation to each note type.
- Ensure every recommended action is suggestion-only and routes through explicit user action later.
- Add tests per note type for context selection, valid output, citations, invalid input, sensitivity handling, and no canonical mutation.

Firecrawl Evidence:

- Use Firecrawl if medical/tax/legal explanation boundaries, comparison UX conventions, timeline extraction conventions, or action-recommendation safety patterns are uncertain.

Exit Criteria:

- All required note types are supported.
- Type-specific constraints are tested.
- Outputs are cited and non-mutating.

## 9.10 Safety Boundaries, Disable Mode, And Redaction Discipline

Goal: make analysis safe to operate on sensitive personal documents without becoming an unbounded advice or data-egress channel.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 9 done and gate.
- `AGENT_START_HERE.md`, local-first and no external critical flows.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, privacy and audit requirements.
- `pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md`, model-serving and editability risks.
- Active settings and observability code.
- Active model gateway and worker code.

Work:

- Add settings for analysis enablement, allowed model profiles, max documents, max pages, max context chars/tokens, max answer chars, max citation excerpt length, timeout, queue priority, and retry limits.
- Ensure default local-first posture: no external model API calls unless explicitly enabled and documented.
- Make disabled mode explicit in API and UI. Disabled mode should return a clear error for POST requests and a clear unavailable state in the workspace.
- Add redaction safeguards for logs, errors, job payload summaries, health snapshots, model traces, and client payloads.
- Prevent analysis from using raw unreviewed handwriting/visual output without uncertainty labels.
- Add tests for disabled mode, external-call guardrails, log redaction, error redaction, max-scope limits, model unavailable, and sensitive document warnings/refusals.

Firecrawl Evidence:

- Use Firecrawl if security logging guidance, local inference configuration, professional-advice disclaimers, redaction conventions, or outbound network controls are uncertain.

Exit Criteria:

- Analysis can be disabled without degrading core product behavior.
- Logs and errors do not leak sensitive content.
- Scope and runtime limits bound analysis cost and risk.

## 9.11 Runtime, Observability, And Admin Visibility

Goal: operate analysis runs with clear job state, bounded resource use, and model availability signals.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, analysis run model and disabled behavior.
- `pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv`, `worker-analysis` and `model-qwen`.
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`, observability and audit requirements.
- `compose.yaml`, analysis profile and model profiles.
- `README.md`.
- Phase 0 job/admin health implementation.
- Phase 4 and Phase 8 model runtime implementation.

Work:

- Ensure `worker-analysis` can run under a profile-gated local configuration and can be absent without failing core services.
- Add service health fields for analysis worker enabled/disabled, queue depth, oldest job age, success/failure counts, model availability, validation failures, timeout counts, and dead-letter counts.
- Keep model-qwen optional for analysis, with clear degraded behavior when unavailable.
- Add admin visibility for analysis jobs through existing jobs/admin surfaces rather than inventing a parallel operations screen.
- Add metrics/logs for job lifecycle and validation class without raw content.
- Update README or implementation notes with analysis profile commands, disabled-mode behavior, and optional live-model validation steps.
- Add tests for health snapshots, queue metrics, model unavailable state, Compose placeholder mode, and admin retry behavior.

Firecrawl Evidence:

- Use Firecrawl if Docker Compose profiles, vLLM health endpoints, model timeout behavior, metrics conventions, or admin status design are uncertain.

Exit Criteria:

- Analysis runtime is observable and bounded.
- Core product services do not depend on the analysis worker.
- Operators can see and retry failed analysis jobs.

## 9.12 Evaluation, QA, And Gate E

Goal: prove citation-backed analysis works on representative documents and respects sensitivity/ACL policy.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 9 gate.
- `AGENT_START_HERE.md`, Gate E.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`, corpus evaluation and GA-like release guidance.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, Epic 8.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`, if UI changed.
- Existing golden corpus, search benchmarks, and test fixture conventions.

Work:

- Add deterministic analysis fixtures for EOB explanation, document comparison, timeline, obligation scan, tax scan, and summary.
- Define expected properties rather than brittle full-text equality: required citations, selected documents, note type, recommended-action shape, absence of canonical mutation, and safety language where applicable.
- Add live-model benchmark hooks that can run against local Qwen when enabled, with stored before/after metrics and manual review notes.
- Add ACL and sensitivity regression cases: unauthorized documents, mixed-sensitivity scopes, hidden related documents, and disabled analysis.
- Add UI QA for frame `14:990` using Figma screenshot comparison, Playwright workflows, responsive states, keyboard focus, and network assertions.
- Confirm Gate E:
  - analysis outputs cite source documents and page references;
  - analysis can be disabled without breaking normal usage;
  - no analysis output overwrites accepted extraction data without explicit user action.

Firecrawl Evidence:

- Use Firecrawl if evaluation metric design, benchmark reporting, citation-scoring methods, Playwright behavior, or safety test conventions are uncertain.

Exit Criteria:

- Citation-backed analysis has automated and, where needed, manual benchmark evidence.
- Gate E is satisfied.
- Regressions in search, review, and canonical facts are tested.

## 9.13 Contract, Static Analysis, Runtime, UI, And Phase 9 Gate

Goal: complete Phase 9 with contract parity, static validation, runtime checks, UI checks, and release notes.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 9 gate.
- `STRUCTURA_PLAN_INDEX.md`, source alignment and stop rules.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`, if UI changed.
- `STRUCTURA_PHASE_9_IMPLEMENTATION_PLAN.md`, all subphase exit criteria.
- Active `README.md`, `Makefile`, CI scripts, test scripts, and validation commands.

Work:

- Run formatting checks, lint, type checking, contract validation, event schema validation, SAST/security checks, tests, web build, and any existing architecture validation scripts.
- Run analysis-specific tests for contracts, ACL, sensitivity, citation validation, disabled mode, no canonical mutation, worker retries, prompt/output validation, and note persistence.
- Run existing regression suites for ingest, viewer, review, search, relationships, visual retrieval, and jobs.
- If UI changed, run Playwright flows for analysis workspace, citation jumps, disabled mode, failure states, comparison, and responsive behavior.
- Run Compose/local smoke tests for API, web, worker-analysis placeholder, model placeholder mode, disabled analysis, and optional live analysis if local model services are available.
- Update README, ADRs, or implementation notes with commands, limitations, prompt/model versions, disabled-mode behavior, and optional live-GPU validation steps.
- Stop after Phase 9. Do not start Phase 10 without explicit user instruction.

Firecrawl Evidence:

- Use Firecrawl if validation tool behavior, SAST configuration, OpenAPI validation, Playwright/browser behavior, model runtime behavior, or deployment conventions are uncertain.

Exit Criteria:

- Contract, static analysis, tests, runtime smokes, and UI checks pass or have clearly documented blockers.
- Phase 9 gate evidence is recorded.
- No Phase 10 implementation is included.

## Stop Point

After Phase 9 is implemented and verified, stop and report:

- Files changed.
- Contracts or schema migrations added.
- Analysis request, worker, note persistence, citation, UI, and disabled-mode behavior implemented.
- Prompt/model versions and validation behavior.
- Benchmark, QA, and Gate E evidence.
- Validation commands and results.
- Known limitations or Phase 10 handoff notes.

Do not continue into Phase 10 until the user explicitly approves the next phase.
