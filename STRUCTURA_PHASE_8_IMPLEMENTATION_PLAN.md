# Structura Phase 8 Implementation Plan

Phase 8 makes difficult documents first-class: low-text scans, handwriting-heavy pages, degraded images, and layout-sensitive documents should be detectable, reviewable, and retrievable without treating uncertain machine output as truth.

This plan expands Phase 8 from `STRUCTURA_IMPLEMENTATION_PLAN.md`. It does not replace the root plan. Use the root plan for phase boundaries and this document for Phase 8 execution detail.

## Operating Rules

- Do not inspect or rely on anything under `archive/`.
- Before coding any subphase, re-read the files listed in that subphase's **Fresh Context** section. Use `wc -l` and bounded `sed -n` chunks for large files so full reads are auditable.
- When an artifact exists in both Markdown and DOCX form, read the Markdown artifact by default. Only inspect DOCX when the user explicitly asks for layout/fidelity review or the Markdown file is missing/incomplete.
- Keep generated FastAPI OpenAPI paths aligned with `contracts/api/openapi.yaml`. If implementation and contract differ, stop and resolve the contract question explicitly.
- Preserve Phase 1-7 invariants: original bytes are immutable, accepted canonical facts remain the default read model, suggested relationships remain reviewable, search indexes are assistive, browser-mutating routes require CSRF, and access control is enforced before returning document-derived content.
- Text retrieval remains the default path. Visual embeddings and Qwen-heavy handwriting routes are selective enhancements for pages where text-only extraction is weak.
- Handwriting and degraded-document outputs default to review-required unless quality is demonstrably high under an explicit policy.
- Do not log raw document text, images, extracted handwriting, model prompts, model responses, object-storage paths, or presigned asset URLs.
- Keep Phase 8 focused on difficult-document detection, selective visual embeddings, handwriting routing, review-required uncertainty, visual retrieval, and benchmark coverage. Do not implement Phase 9 chat, comparison, analysis, or Phase 10 exports.

## Firecrawl Evidence Rule

When APIs, external contracts, library behavior, security conventions, OpenAPI semantics, FastAPI/Pydantic behavior, PostgreSQL/pgvector behavior, BM25/vector fusion, model-serving APIs, Qwen/Granite/vLLM behavior, image preprocessing, OCR/handwriting conventions, visual embedding dimensions, accessibility conventions, React/Vite behavior, or Playwright behavior are in play, search online with Firecrawl if there is any uncertainty.

Use primary sources where possible: official framework documentation, standards documents, official package docs, project repositories, security guidance, model cards, or vendor docs. Save Firecrawl outputs under `.firecrawl/`, read them incrementally, and summarize the evidence in implementation notes or ADRs when it affects a decision. Do not use unsourced memory to settle uncertain API, schema, database, model, image-processing, browser, worker, or security behavior.

## Phase 8 Required Artifact Set

The full Phase 8 artifact list from `STRUCTURA_IMPLEMENTATION_PLAN.md` remains required context:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
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

The duplicate DOCX entries in the root plan are intentionally omitted here under the current repo guidance.

## 8.0 Baseline Reconciliation

Goal: confirm the existing parse, extraction, embedding, review, and search foundation can support Phase 8 without drifting from contracts or schemas.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 8 section.
- `STRUCTURA_PHASE_3_IMPLEMENTATION_PLAN.md`, preview/page assets, Docling output, page rows, chunks, and parse quality.
- `STRUCTURA_PHASE_4_IMPLEMENTATION_PLAN.md`, extraction routes, Qwen/Granite gateway, candidates, review tasks, and canonical promotion.
- `STRUCTURA_PHASE_5_IMPLEMENTATION_PLAN.md`, BM25, text embeddings, filter-aware planner, hybrid RRF, and benchmark gates.
- `STRUCTURA_PHASE_7_IMPLEMENTATION_PLAN.md`, relationship/timeline search integration and ACL invariants.
- `agents.md`.
- `.wolf/cerebrum.md`.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, Qwen3-VL, routing policy, semantic retrieval, and visual retrieval sections.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, difficult document handling and visual retrieval section.
- `pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md`, handwriting and model routing rules.
- `pro-merged-master-v1.2/docs/18_Filter_Aware_Vector_Search_Addendum.md`, filter-aware vector retrieval and hybrid fusion.
- `contracts/api/openapi.yaml`.
- `contracts/events/embed_document_job.v1.schema.json`.
- `contracts/events/extract_document_job.v1.schema.json`.
- `database/020_core_tables.sql`.
- `database/040_indexes_bm25_pgvector.sql`.
- `compose.yaml`.
- `infrastructure/runtime_service_matrix.csv`.

Work:

- Confirm page image assets, thumbnails, OCR confidence, text chunks, text embeddings, extraction worker routes, model gateway, review tasks, and search planner exist from earlier phases.
- Confirm the active `embeddings` schema supports `owner_type = page`, `owner_type = asset`, `modality = visual`, `modality = mixed`, dimension validation, active/inactive rows, and model profile metadata.
- Confirm the active pgvector indexes include the intended text and visual dimensions. The artifact plan assumes text embeddings around 1536 dimensions and visual embeddings around 1024 dimensions; verify before implementation.
- Reconcile OpenAPI with Phase 8 needs. The plan allows either a dedicated visual retrieval endpoint or a hybrid inclusion policy that folds visual candidates into existing search. Decide explicitly and update contracts plus implementation together if the public API changes.
- Identify implementation modules for difficult-document detection, visual embedding scheduling, visual embedding worker code, Qwen-heavy handwriting routing, review-required policy, visual candidate retrieval, hybrid fusion, UI cues, benchmarks, and observability.
- Record any schema/API/model-profile decision in an ADR or implementation note if it affects future phases.

Firecrawl Evidence:

- Use Firecrawl if visual embedding dimensions, pgvector index behavior, vLLM/model-serving APIs, FastAPI/OpenAPI extension strategy, or model-profile conventions are uncertain.

Exit Criteria:

- Phase 8 boundaries are known.
- Contract gaps are resolved or explicitly deferred.
- Visual and handwriting work will not bypass review, ACL, or canonical fact authority.

## 8.1 Page Quality Signals And Difficult-Document Detection

Goal: detect pages and documents that need visual handling, handwriting routing, or review-required uncertainty.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 8 task list.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, difficult documents, Qwen3-VL role, and visual retrieval rationale.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, low-text, handwriting, degraded scan, and complex-layout handling.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`, golden corpus requirements for handwritten notes and low-quality scans.
- `pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md`, handwriting accuracy risk and review-required mitigation.
- `database/020_core_tables.sql`, `documents`, `document_pages`, `document_assets`, and review-related tables.
- Phase 3 parse quality and page asset code.
- Phase 4 review task service.

Work:

- Add a deterministic difficult-document classifier that runs after parsing/OCR and before embedding/extraction decisions.
- Detect at least these signals: low text density, missing text layer, low OCR confidence, handwriting-heavy pages, visually degraded scans, complex layout, high table/image density, parse warnings, and pages where text chunks are sparse or empty.
- Persist page-level and document-level signal summaries in existing metadata fields where available. If current schema cannot represent the needed data safely, add a scoped migration with tests.
- Set or derive `documents.has_handwriting`, `documents.is_digital_native`, `document_pages.has_text_layer`, OCR confidence, and quality metadata consistently.
- Emit review tasks or review flags when handwriting/degradation makes extracted facts uncertain.
- Make detection idempotent so reprocessing a page updates the current signal summary without duplicating review tasks.
- Add tests for low-text scans, text-layer PDFs, handwriting-heavy pages, degraded image pages, complex layouts, mixed documents, and rerun idempotency.

Firecrawl Evidence:

- Use Firecrawl if OCR confidence semantics, image-quality heuristics, handwriting detection libraries, or PDF/page-rendering conventions are uncertain.

Exit Criteria:

- Difficult pages are explicitly flagged with machine-readable reasons.
- Handwriting and degraded pages create review-required behavior unless a later policy proves high confidence.
- Detection is repeatable and covered by fixtures.

## 8.2 Selective Visual Embedding Policy And Model Profile

Goal: define when visual embeddings are created and which model profile/dimension/index policy owns them.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, selective visual embedding task.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, semantic and visual retrieval.
- `pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md`, text versus visual embedding separation.
- `pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md`, open questions about embedding models and dimensions.
- `pro-merged-master-v1.2/docs/18_Filter_Aware_Vector_Search_Addendum.md`, vector search filter behavior.
- `contracts/events/embed_document_job.v1.schema.json`.
- `database/020_core_tables.sql`, `embeddings`.
- `database/040_indexes_bm25_pgvector.sql`, text, visual, and mixed vector indexes.
- `infrastructure/runtime_service_matrix.csv`, `worker-embeddings` and `model-embed`.

Work:

- Define a visual embedding eligibility policy from Phase 8 signals: low text, handwriting, degraded scan, image-heavy page, visually distinctive form, layout-sensitive page, and explicit re-embed request.
- Keep text embeddings default for normal text-heavy pages. Visual embeddings should be selective to control cost, latency, and index size.
- Define embedding owner granularity: page-level first, crop/element-level only when prior phases expose reliable element images and retrieval requires them.
- Define model profile metadata, dimension expectations, batching limits, retry behavior, and invalidation rules.
- Validate that `embed_document_job.v1` can express `modalities = visual` and `modalities = mixed`, target owner types, and forced re-embedding. Extend the contract only if necessary.
- Add policy tests for eligible/non-eligible documents, forced re-embedding, changed page assets, model-profile changes, and dimension mismatch rejection.

Firecrawl Evidence:

- Use Firecrawl if visual embedding model dimensions, batching constraints, model-serving API contracts, or pgvector index requirements are uncertain. Prefer model cards, official docs, and pgvector docs.

Exit Criteria:

- Visual embeddings have an explicit eligibility policy.
- Model profile and dimension assumptions are verified or recorded as configurable placeholders.
- Text-only documents are not needlessly embedded visually.

## 8.3 Visual Embedding Worker And Persistence

Goal: generate, validate, and persist visual embeddings for eligible page/image assets.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, visual embedding and retrieval tasks.
- `STRUCTURA_PHASE_5_IMPLEMENTATION_PLAN.md`, embedding gateway/worker and semantic retrieval implementation.
- `pro-merged-master-v1.2/contracts/events/embed_document_job.v1.schema.json`.
- `pro-merged-master-v1.2/database/020_core_tables.sql`, `document_pages`, `document_assets`, `embeddings`, and job tables.
- `pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql`.
- `pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv`.
- `compose.yaml`, `worker-embeddings`, `model-embed`, and model placeholders.
- Active embedding service code and tests.

Work:

- Extend the embedding worker to accept visual and mixed modalities without regressing text embeddings.
- Load eligible page images or asset previews through the protected internal storage path, not public URLs.
- Preprocess images deterministically for the embedding model: orientation, colorspace, size limits, and format conversion.
- Validate returned vector dimensions before persistence. Reject or dead-letter incompatible model output instead of inserting malformed rows.
- Persist visual embeddings with owner type, owner id, model id/profile, dimension, modality, metadata, and active status.
- Invalidate or supersede old visual embeddings when page assets, model profiles, or eligibility signals change.
- Add worker tests for visual job claim, page image lookup, missing asset failure, model timeout, dimension mismatch, idempotent rerun, active row replacement, and mixed text/visual job handling.

Firecrawl Evidence:

- Use Firecrawl if image preprocessing behavior, Pillow/PDF rendering APIs, model gateway request/response shapes, or pgvector vector insertion semantics are uncertain.

Exit Criteria:

- Eligible pages receive visual embeddings.
- Bad model output cannot poison the vector index.
- Text embedding behavior remains unchanged.

## 8.4 Qwen-Heavy Handwriting Route

Goal: route handwriting-heavy and degraded pages through Qwen-heavy extraction/transcription while keeping uncertain output review-required.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Qwen-heavy handwriting route task.
- `STRUCTURA_PHASE_4_IMPLEMENTATION_PLAN.md`, model gateway, extraction routes, candidates, validators, and review actions.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, Qwen3-VL role and routing policy.
- `pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md`, handwritten note path and review-required rule.
- `pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md`, handwriting accuracy risk.
- `contracts/events/extract_document_job.v1.schema.json`.
- `contracts/schemas/common_defs.schema.json`, confidence summary and evidence references.
- `database/020_core_tables.sql`, extraction, candidate, review, asset, and page tables.
- `infrastructure/runtime_service_matrix.csv`, `worker-extraction`, `model-qwen`, and `model-granite`.

Work:

- Add or formalize a route profile for handwriting-heavy pages, such as `qwen_primary_review_required`, using the existing extraction job contract where possible.
- Route target pages to Qwen when detection indicates handwriting, low text, degraded visual quality, or ambiguous layout where text-only extraction is insufficient.
- Persist Qwen transcription/extraction output as candidate facts with source engine, evidence refs, confidence summary, page refs, and review-required status.
- Keep Granite or deterministic validators available for structured fields where useful, but do not let secondary validation silently promote uncertain handwriting output.
- Default handwritten transcriptions and facts to review-required unless the explicit quality policy says otherwise.
- Ensure accepted canonical facts only change through the existing review/canonical promotion path.
- Add tests for handwritten note routing, target page selection, Qwen timeout/failure, candidate persistence, review-required default, high-quality exception policy, and no silent canonical promotion.

Firecrawl Evidence:

- Use Firecrawl if Qwen3-VL prompt/API behavior, vLLM multimodal request format, structured output constraints, or confidence calibration conventions are uncertain.

Exit Criteria:

- Handwriting-heavy pages use the intended Qwen-heavy route.
- Handwriting-derived facts are reviewable and evidence-backed.
- Canonical data is not changed silently by uncertain handwriting output.

## 8.5 Review-Required Uncertainty And UI Cues

Goal: make difficult-document uncertainty visible in review, viewer, and search surfaces without overwhelming normal workflows.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, done criteria and Phase 8 gate.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`, UI QA process and stop rules.
- `STRUCTURA_PHASE_4_IMPLEMENTATION_PLAN.md`, review queue and evidence inspector.
- `STRUCTURA_PHASE_5_IMPLEMENTATION_PLAN.md`, search result and evidence display.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, review behavior and document viewer expectations.
- `pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md`, review-required defaults.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md` if implementation touches review language or visual treatment.
- Active web review, viewer, and search UI code.

Work:

- Surface document/page quality signals in the document viewer and review queue where they affect trust: handwriting, low text, degraded scan, and complex layout.
- Show page-level evidence and thumbnails for handwriting or visual extraction candidates.
- Mark handwriting-derived fields and transcriptions as review-required until accepted.
- Make search results that came from visual/mixed retrieval identify the source type without exposing hidden data or raw embedding internals.
- Preserve existing visual design language and Figma QA requirements. If UI ambiguity remains after reading Figma/artifacts, stop and ask the user before inventing a new pattern.
- Add accessibility and UI tests for uncertainty labels, review action flows, evidence thumbnails, search result source labels, and mobile/desktop layout.

Firecrawl Evidence:

- Use Firecrawl if accessibility conventions, ARIA behavior, browser APIs, React/Vite behavior, or Playwright testing behavior are uncertain.

Exit Criteria:

- Users can see why difficult-document output needs review.
- Review actions remain clear and auditable.
- Visual/mixed retrieval explanations do not leak protected content.

## 8.6 Visual Retrieval Contract And API Policy

Goal: expose visual retrieval through a contract-safe API without creating an undocumented search surface.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, visual retrieval endpoint or hybrid inclusion policy task.
- `STRUCTURA_PHASE_5_IMPLEMENTATION_PLAN.md`, search API, hybrid retrieval, filters, facets, and saved searches.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, visual retrieval use cases.
- `pro-merged-master-v1.2/docs/18_Filter_Aware_Vector_Search_Addendum.md`, hybrid retrieval and filter-aware vector search.
- `contracts/api/openapi.yaml`, search endpoints, modes, result schemas, and error responses.
- `database/025_baseline_identity_acl_candidate_rules.sql`, ACL policy baseline.
- `database/040_indexes_bm25_pgvector.sql`, vector indexes.
- Active search routes, DTOs, and search services.

Work:

- Decide the public API approach:
  - add a documented visual retrieval endpoint or search mode, or
  - include visual candidates inside existing hybrid search under an explicit policy.
- Update `contracts/api/openapi.yaml`, generated/handwritten DTOs, route tests, and API implementation together for any public contract change.
- Define accepted request shapes, query/image inputs if any, filter behavior, pagination, result scoring fields, explanations, and error responses.
- Enforce ACL before returning results, counts, snippets, thumbnails, page ids, or visual evidence.
- Do not accept arbitrary image search uploads unless the contract, storage policy, privacy model, and abuse controls are explicitly defined.
- Add tests for contract parity, visual/hybrid request validation, ACL filtering, pagination, no hidden result leaks, result explanations, and unsupported mode errors.

Firecrawl Evidence:

- Use Firecrawl if OpenAPI schema design, image-search API conventions, FastAPI file handling, pgvector query behavior, or search-result scoring conventions are uncertain.

Exit Criteria:

- Visual retrieval has one documented API policy.
- Contract and implementation remain in sync.
- Access control is enforced before any result leaves the API.

## 8.7 Mixed Hybrid Retrieval And Optional Multimodal Reranker

Goal: blend lexical, text-vector, and visual-vector signals so difficult documents can be found without harming normal search quality.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, visual retrieval task.
- `STRUCTURA_PHASE_5_IMPLEMENTATION_PLAN.md`, BM25, semantic retrieval, RRF, filter-aware planner, and golden benchmarks.
- `pro-merged-master-v1.2/docs/18_Filter_Aware_Vector_Search_Addendum.md`, hybrid fusion, filters, oversampling, and ACL-final requirements.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, visual retrieval scenarios.
- `database/040_indexes_bm25_pgvector.sql`.
- Active search planner, retrieval, ranking, and test code.

Work:

- Add visual-vector candidate retrieval for eligible pages/assets when query policy indicates it should run.
- Fuse lexical, text-vector, and visual-vector candidates with a transparent policy such as reciprocal rank fusion, weighted blending, or another documented method.
- Keep lexical/BM25 and text-vector retrieval active so normal text-heavy search does not depend on visual vectors.
- Support filter-aware oversampling for visual candidates, then enforce ACL and final filters before response construction.
- Add explanations that identify lexical, semantic, visual, or mixed contribution without exposing internal embeddings.
- Treat multimodal reranking as optional and disabled unless a configured model profile, benchmark improvement, and contract-safe result explanation are available.
- Add tests for visual-only hit, text+visual overlap, filter-aware visual retrieval, ACL-final suppression, score explanation, reranker disabled behavior, and hybrid regression benchmarks.

Firecrawl Evidence:

- Use Firecrawl if RRF/fusion behavior, pgvector query plans, iterative scans, multimodal reranker APIs, or benchmark methodology are uncertain.

Exit Criteria:

- Low-text and visual documents can be retrieved through the selected API policy.
- Normal search quality does not regress.
- Result explanations remain understandable and safe.

## 8.8 Low-Text Indexing And Retrieval Fallbacks

Goal: make low-text documents discoverable even when OCR and text chunks are sparse.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, low-text retrieval and benchmark tasks.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, sparse/noisy text indexing and layout-sensitive retrieval.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`, search benchmark expectations.
- `pro-merged-master-v1.2/docs/18_Filter_Aware_Vector_Search_Addendum.md`, BM25/vector fallback behavior.
- `database/020_core_tables.sql`, document metadata, pages, chunks, canonical facts, and embeddings.
- Active Phase 3 chunking, Phase 4 extraction/candidate, and Phase 5 indexing code.

Work:

- Ensure documents with sparse text still contribute searchable metadata: filename, title, type, dates, contacts, folders, tags, canonical facts, reviewed transcriptions, and page-level summaries when available.
- Use OCR rescue or page-level generated descriptions only when the output is clearly labeled as machine-generated and reviewable.
- Avoid indexing unreviewed uncertain handwriting as authoritative canonical text.
- Add layout-sensitive fallback fields when form shape, page type, table location, or image-heavy structure can improve retrieval.
- Ensure reindexing occurs when review accepts corrected handwriting/transcription or when visual embeddings become available.
- Add tests for no-text page retrieval by metadata, reviewed transcription retrieval, unreviewed handwriting uncertainty, reindex after acceptance, and query behavior for visually distinctive pages.

Firecrawl Evidence:

- Use Firecrawl if OCR fallback behavior, generated-description indexing conventions, BM25 indexing of sparse fields, or pgvector/BM25 blending details are uncertain.

Exit Criteria:

- Low-text documents are not invisible.
- Reviewed human corrections improve future retrieval.
- Unreviewed uncertain text is not presented as authoritative.

## 8.9 Difficult-Document Benchmarks And Golden Samples

Goal: prove Phase 8 behavior with golden low-text, handwriting, degraded scan, and layout-sensitive samples.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, low-text benchmark and Phase 8 gate.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`, golden corpus, handwritten notes, messy scanned receipts, and search metrics.
- `pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md`, handwriting risk.
- `STRUCTURA_PHASE_5_IMPLEMENTATION_PLAN.md`, search benchmark harness.
- Existing test fixture directories, golden sample conventions, and benchmark scripts.

Work:

- Add or identify fixture samples for handwritten notes, low-text pages, degraded scans, image-heavy receipts/forms, and complex layouts.
- Define expected detection signals, review-required behavior, retrieval queries, top-k expectations, evidence expectations, and failure tolerances.
- Extend the benchmark harness to measure visual/mixed retrieval without hiding lexical/text-vector regressions.
- Include negative cases where visual retrieval should not run or should not outrank stronger text matches.
- Add CI-friendly tests that can run with deterministic placeholders while preserving separate live-model benchmark hooks for GPU/model validation.
- Document how to run local deterministic tests and optional model-backed benchmarks.

Firecrawl Evidence:

- Use Firecrawl if benchmark metric definitions, OCR/handwriting evaluation practices, or search relevance measurement conventions are uncertain.

Exit Criteria:

- Phase 8 has explicit benchmark coverage for low-text and handwriting samples.
- Review-required behavior is asserted, not manual.
- Benchmarks detect both visual-retrieval failures and normal-search regressions.

## 8.10 Runtime, Resource, And Observability

Goal: keep visual embeddings and handwriting routes operationally bounded on local and GPU runtimes.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, runtime expectations for Phase 8.
- `pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv`.
- `compose.yaml`.
- `STRUCTURA_PHASE_4_IMPLEMENTATION_PLAN.md`, model gateway and extraction worker runtime.
- `STRUCTURA_PHASE_5_IMPLEMENTATION_PLAN.md`, embedding worker runtime.
- Active settings, worker, service-health, and observability code.

Work:

- Confirm service ownership and resource boundaries for `worker-extraction`, `worker-embeddings`, `model-qwen`, `model-granite`, and `model-embed`.
- Add runtime settings for visual embedding enablement, batch size, max image pixels/bytes, model profile, timeout, retry, and queue concurrency.
- Add health checks or service-health snapshots that distinguish text embedding, visual embedding, Qwen handwriting, and model unavailable states.
- Add structured metrics/logs for counts, latency, failure class, retry/dead-letter behavior, and benchmark runs without logging document content or image data.
- Ensure Compose profiles and placeholder model services allow deterministic local tests without requiring GPU services.
- Add tests for disabled visual embedding mode, model unavailable behavior, retry/backoff, health snapshot fields, and redacted logs.

Firecrawl Evidence:

- Use Firecrawl if vLLM health endpoints, model-serving timeout behavior, GPU batching guidance, Docker Compose conventions, or observability/security conventions are uncertain.

Exit Criteria:

- Phase 8 can run deterministically without a GPU and validate live-model behavior when GPU services are enabled.
- Operational failures are visible without leaking private content.
- Resource usage is bounded by settings.

## 8.11 Integration, Security, And Regression Coverage

Goal: validate the end-to-end difficult-document flow and its security boundaries.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 8 done and gate.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`.
- `pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql`.
- `contracts/api/openapi.yaml`.
- `contracts/events/embed_document_job.v1.schema.json`.
- `contracts/events/extract_document_job.v1.schema.json`.
- Phase 1 protected asset streaming tests.
- Phase 2 ACL/audit tests.
- Phase 4 review and extraction tests.
- Phase 5 search/security tests.
- Active test suites.

Work:

- Add integration coverage for ingesting a low-text or handwritten document, detecting difficult pages, creating visual embeddings, routing handwriting extraction, creating review tasks, and retrieving the document through the selected visual/hybrid policy.
- Assert ACL behavior across every returned surface: search results, page refs, thumbnails, evidence, review tasks, logs, and API errors.
- Verify browser-mutating routes still require CSRF and API-token routes remain protected.
- Add contract tests for API path parity, event schema validation, and DTO compatibility.
- Add static checks or grep-based safeguards for raw model output/image/text logging if dedicated SAST rules are not yet available.
- Add regression tests proving text-only search, text embeddings, canonical fact reads, relationships, and filing rules still work.

Firecrawl Evidence:

- Use Firecrawl if security guidance, CSRF behavior, OpenAPI validation tooling, SAST rule behavior, or framework test conventions are uncertain.

Exit Criteria:

- The full difficult-document pipeline is tested.
- No protected content leaks through visual retrieval or review surfaces.
- Earlier phase behavior has explicit regression coverage.

## 8.12 Contract, Static Analysis, Runtime, UI, And Phase 8 Gate

Goal: complete Phase 8 with contract parity, static validation, runtime checks, UI checks, and gate evidence.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 8 gate.
- `STRUCTURA_PLAN_INDEX.md`, source alignment and stop rules.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`, if UI changed.
- `STRUCTURA_PHASE_8_IMPLEMENTATION_PLAN.md`, all subphase exit criteria.
- Active `README.md`, `Makefile`, CI scripts, test scripts, and validation commands.

Work:

- Run formatting checks, lint, type checking, contract validation, event schema validation, SAST/security checks, tests, web build, and any existing architecture validation scripts.
- Run benchmark checks for low-text and handwriting samples. Capture expected review-required behavior and retrieval metrics.
- If UI changed, run Playwright flows for review, viewer, and search surfaces across required viewports. Use screenshots/pixel checks where the Figma QA plan requires them.
- Run Compose/local smoke tests for API, web, workers, model placeholders, text embeddings, visual embeddings, and Qwen-route fallback behavior.
- Update README or implementation notes with commands, limitations, configuration, model-profile assumptions, and optional live-GPU validation steps.
- Confirm the Phase 8 gate: low-text and handwriting samples have explicit review behavior and benchmark coverage.
- Stop after Phase 8. Do not start Phase 9 without explicit user instruction.

Firecrawl Evidence:

- Use Firecrawl if validation tool behavior, Playwright/browser behavior, SAST tool configuration, OpenAPI validation, model runtime behavior, or deployment conventions are uncertain.

Exit Criteria:

- Contract, static analysis, tests, runtime smokes, and UI checks pass or have clearly documented blockers.
- Phase 8 gate evidence is recorded.
- No Phase 9 or Phase 10 implementation is included.

## Stop Point

After Phase 8 is implemented and verified, stop and report:

- Files changed.
- Contracts or schema migrations added.
- Detection, handwriting, visual embedding, and retrieval behavior implemented.
- Benchmark and review-required evidence.
- Validation commands and results.
- Known limitations or Phase 9 handoff notes.

Do not continue into Phase 9 until the user explicitly approves the next phase.
