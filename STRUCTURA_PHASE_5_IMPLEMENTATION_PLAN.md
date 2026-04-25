# Structura Phase 5 Implementation Plan

Phase 5 makes the corpus retrievable through lexical, semantic, and filter-aware hybrid search. It turns the Phase 3 canonical parse and Phase 4 accepted facts into search surfaces without treating search indexes as the system of record.

This plan expands Phase 5 from `STRUCTURA_IMPLEMENTATION_PLAN.md`. It does not replace the root plan. Use the root plan for phase boundaries and this document for Phase 5 execution detail.

## Operating Rules

- Do not inspect or rely on anything under `archive/`.
- Before coding any subphase, re-read the files listed in that subphase's **Fresh Context** section. Use `wc -l` and bounded `sed -n` chunks for large files so full reads are auditable.
- When an artifact exists in both Markdown and DOCX form, read the Markdown artifact by default. Only inspect DOCX when the user explicitly asks for layout/fidelity review or the Markdown file is missing/incomplete.
- Keep generated FastAPI OpenAPI paths aligned with `contracts/api/openapi.yaml`. If implementation and contract differ, stop and resolve the contract question explicitly.
- Search indexes are assistive. The source of truth remains Postgres records, object storage, versioned parse/extraction artifacts, canonical facts, and review history.
- Apply authorization and household/folder ACL filters authoritatively before returning any result. Never rely on UI filters or vector candidate filtering as the final access-control boundary.
- Do not leak raw object-store paths, filesystem paths, raw model output, raw full document text, or unredacted sensitive fields in logs, job payloads, search debug responses, or frontend telemetry.
- Keep Phase 5 focused on lexical search, embeddings, semantic retrieval, filter-aware hybrid fusion, result explanations, search UI, and Gate D. Do not implement Phase 7 relationships/timelines, Phase 8 visual retrieval beyond reserved hooks, Phase 9 analysis, or Phase 10 exports except for contract-safe placeholders already present.

## Firecrawl Evidence Rule

When APIs, external contracts, library behavior, security conventions, OpenAPI semantics, FastAPI/Pydantic behavior, PostgreSQL/SQL behavior, ParadeDB `pg_search`, BM25 scoring/snippets/facets, pgvector HNSW behavior, vector filtering, embedding model dimensions, model-serving APIs, reranker APIs, React/Vite conventions, Playwright behavior, or UI accessibility conventions are in play, search online with Firecrawl if there is any uncertainty.

Use primary sources where possible: official framework documentation, standards documents, official package docs, project repositories, model cards, or vendor docs. Save Firecrawl outputs under `.firecrawl/`, read them incrementally, and summarize the evidence in implementation notes or ADRs when it affects a decision. Do not use unsourced memory to settle uncertain API, schema, database, model, browser, worker, or security behavior.

## Phase 5 Required Artifact Set

The full Phase 5 artifact list from `STRUCTURA_IMPLEMENTATION_PLAN.md` remains required context:

```text
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/AGENT_START_HERE.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/01_App_Specification.md
/Users/brennanconley/vibecode/structura/pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md
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

The duplicate DOCX entries in the root plan are intentionally omitted here under the current repo guidance.

## 5.0 Baseline Reconciliation

Goal: confirm Phase 4 produces searchable source material and identify the exact implementation files Phase 5 will change.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 5 section.
- `STRUCTURA_PHASE_3_IMPLEMENTATION_PLAN.md`, canonical chunk/page/table commitments.
- `STRUCTURA_PHASE_4_IMPLEMENTATION_PLAN.md`, candidate/canonical fact commitments and Gate C.
- `agents.md`.
- `.wolf/cerebrum.md`.
- `pro-merged-master-v1.2/AGENT_START_HERE.md`, Gate D.
- `pro-merged-master-v1.2/docs/18_Filter_Aware_Vector_Search_Addendum.md`.
- `database/020_core_tables.sql`.
- `database/025_baseline_identity_acl_candidate_rules.sql`.
- `database/040_indexes_bm25_pgvector.sql`.
- `database/050_views_and_functions.sql`.
- `contracts/api/openapi.yaml`.
- `apps/api/structura_api/routes_documents.py`.
- `compose.yaml`.

Work:

- Confirm Gate C is complete: accepted canonical facts exist, review tasks are generated, manual corrections are auditable, and canonical facts are the default accepted-fact read model.
- Confirm Phase 3 chunk rows exist with stable IDs, page ranges, text content, markdown content, and metadata.
- Confirm Phase 4 populates canonical fact data that can enrich search snippets and filters without reading candidate tables as accepted truth.
- Reconcile active SQL and contract files with artifact-pack SQL and OpenAPI.
- Identify where search services, embedding workers, DTOs, query planner modules, UI routes/components, and tests will live.
- Decide whether existing migrations already include required BM25/vector indexes or whether additive migration work is needed for runtime compatibility.
- Confirm the selected embedding profile for the first implementation slice. If the production embedding model and dimension are not settled, default to a fixture/deterministic embedding adapter plus explicit model-profile configuration.

Firecrawl Evidence:

- Use Firecrawl if ParadeDB extension syntax, `pdb.score`, `pdb.snippet`, BM25 index constraints, pgvector HNSW indexing, vector dimensions, or embedding model behavior is uncertain.

Exit Criteria:

- Search dependencies are known.
- Implementation boundaries are identified.
- Any contract/schema/index mismatch is either fixed before coding or documented as an explicit blocker.

## 5.1 Search Contract DTOs And Query Parser

Goal: implement the API contract and validated query/filter model before writing ranking code.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `5C. Filter-Aware Hybrid Search`.
- `pro-merged-master-v1.2/contracts/api/openapi.yaml`, `/api/v1/search`, `SearchRequest`, `SearchResponse`, and `SearchResult`.
- `contracts/api/openapi.yaml`, active search contract.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, search and retrieval requirements.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, Epic 6.
- `pro-merged-master-v1.2/docs/18_Filter_Aware_Vector_Search_Addendum.md`.
- `lib/contracts/registry.py`.
- `apps/api/structura_api/routes_documents.py`.

Work:

- Define typed request/response DTOs for search that match OpenAPI casing and validation behavior.
- Support `mode`: `lexical`, `semantic`, and `hybrid`, with `hybrid` as default.
- Parse filters for family, folder IDs, tags, review state, date ranges, amount ranges, sensitivity, primary folder, and indexed status where contract-compatible.
- Keep unsupported-but-planned filters explicit rather than silently ignoring them.
- Enforce safe limits, deterministic sort defaults, query length bounds, and normalized query text.
- Define a search trace/debug structure for development that never returns restricted candidate rows or sensitive raw text by default.
- Add tests for schema validation, filter parsing, bad filters, default mode, limit clamping, OpenAPI parity, and no silent filter drops.

Firecrawl Evidence:

- Use Firecrawl if FastAPI/Pydantic request validation, OpenAPI schema generation, filter grammar conventions, or query-parameter/body design is uncertain.

Exit Criteria:

- `/api/v1/search` accepts contract-valid requests.
- Invalid requests fail predictably.
- The parsed query object can feed lexical, semantic, and hybrid paths.

## 5.2 Search Projection And Index Readiness

Goal: make chunks and documents carry enough denormalized context for fast filtered retrieval.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `5A. BM25 Search` and `5C. Filter-Aware Hybrid Search`.
- `pro-merged-master-v1.2/docs/18_Filter_Aware_Vector_Search_Addendum.md`, chunk projection requirements.
- `pro-merged-master-v1.2/database/020_core_tables.sql`, `documents`, `document_chunks`, `folders`, `tags`, `saved_searches`, and `embeddings`.
- `pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql`, `document_chunks` projection columns and household indexes.
- `pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql`.
- `pro-merged-master-v1.2/database/050_views_and_functions.sql`.
- `database/`.
- `lib/db/migrations.py`.

Work:

- Ensure `document_chunks` projection columns are populated or backfilled: household, document family, subtype, document date, sensitivity, counterparty, primary folder, and BM25 text.
- Define the projection refresh path after document upload, organization edits, classification, canonical extraction, and manual correction.
- Confirm BM25 indexes cover documents, chunks, and parties without violating ParadeDB's one-BM25-index-per-table rule.
- Confirm B-tree/trigram/GIN indexes support common filters, facets, and folder/tag joins.
- Confirm pgvector partial expression indexes match the configured embedding dimensions.
- Add migration or refresh tests for projection updates, backfill idempotency, and index-creation compatibility.

Firecrawl Evidence:

- Use Firecrawl if ParadeDB index limitations, JSONB indexing, trigram indexes, pgvector partial expression indexes, or migration compatibility is uncertain.

Exit Criteria:

- Searchable rows have denormalized filter context.
- Index definitions are compatible with the active Postgres/ParadeDB/pgvector runtime.
- Projection refresh is idempotent.

## 5.3 Lexical BM25 Search

Goal: implement precise keyword search over documents, chunks, and parties with snippets and grouping.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `5A. BM25 Search`.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, lexical search requirements and latency target.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, BM25 indexing subphase.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, Story 6.1.
- `pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql`.
- `pro-merged-master-v1.2/database/070_query_examples.sql`, lexical examples.
- `contracts/api/openapi.yaml`, `SearchResult`.

Work:

- Implement lexical candidate retrieval over `document_chunks` first, with document-level fallback for title, filename, counterparty, description, and filing notes.
- Include party/contact name hits where available without returning unrelated party rows as document results.
- Use BM25 scores for rank ordering inside the lexical path.
- Return snippets/highlights where ParadeDB supports them, falling back to safe bounded excerpts when it does not.
- Group chunk hits by document while preserving the best matched chunk and page reference.
- Apply household, deleted-state, lifecycle, folder, tag, date, amount, review, and sensitivity filters before returning results.
- Add facets for families, folders, tags, review status, and date buckets when feasible.
- Add tests for exact identifiers, names, claim IDs, phrase-heavy queries, snippet generation, grouping, facets, filter composition, and ACL exclusion.

Firecrawl Evidence:

- Use Firecrawl to verify ParadeDB BM25 query operators, score ordering, snippets, facets, and current extension behavior before relying on syntax that is not already proven locally.

Exit Criteria:

- Exact identifiers, names, claims, and terms are findable.
- Lexical snippets or safe excerpts are returned where relevant.
- Lexical results respect ACL and filters.

## 5.4 Embedding Profile And Gateway

Goal: add an embedding abstraction without coupling search logic to one model server or dimension.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `5B. Embeddings`.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, semantic retrieval and embedding assumptions.
- `pro-merged-master-v1.2/docs/10_Architectural_Decision_Record_Summary.md`, ADR-013.
- `pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md`, text/visual embedding separation.
- `pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md`, embedding model/dimension open question.
- `pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv`, `worker-embeddings` and `model-embed`.
- `compose.yaml`.
- `lib/models/`.

Work:

- Define embedding model profiles with name, version, modality, dimension, distance metric, endpoint, batching limits, and active/default flags.
- Implement an embedding gateway interface with deterministic fixture adapter, local model placeholder adapter, and room for a real `model-embed` HTTP adapter.
- Keep text embeddings as the default search path. Reserve visual/mixed embeddings for later or explicit advanced modes unless Phase 5 implementation requires a hook.
- Validate that emitted vectors match the configured dimension before persistence.
- Persist model metadata with each vector and mark old vectors inactive on re-embed.
- Add tests for dimension validation, model metadata, gateway failure handling, deterministic fixture behavior, and no external API calls in default local flows.

Firecrawl Evidence:

- Use Firecrawl to verify current Qwen3 embedding model cards, output dimensions, vLLM or transformers embedding endpoints, pgvector distance conventions, and any model-server API behavior before implementing a real adapter.

Exit Criteria:

- Search code depends on an embedding gateway, not a hard-coded model.
- Model dimensions and versions are explicit.
- Default local tests do not need a real model server.

## 5.5 Embedding Worker And Idempotent Persistence

Goal: generate and persist embeddings for chunks and document-level representations through background jobs.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `5B. Embeddings`.
- `pro-merged-master-v1.2/contracts/events/embed_document_job.v1.schema.json`.
- `contracts/events/embed_document_job.v1.schema.json`.
- `pro-merged-master-v1.2/database/020_core_tables.sql`, `embeddings`.
- `pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql`, HNSW indexes.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`, embedding persistence tests.
- `lib/jobs/service.py`.
- `workers/`.
- `compose.yaml`, `worker-embeddings`.

Work:

- Implement `embed_document_job` consumption for text chunk embeddings and optional document-level summary/title metadata embeddings.
- Validate job payloads against `embed_document_job.v1.schema.json`.
- Build source text from canonical chunks plus selected metadata/canonical accepted facts without embedding private debug output or raw model output.
- Make embedding generation idempotent: unchanged source/model/profile does not duplicate active embeddings; `force_reembed` supersedes safely.
- Persist embeddings with owner type, owner ID, document ID, model name/version, modality, dimension, metadata, active flag, and timestamps.
- Track job status, retries, failure reasons, and service health.
- Add tests for job validation, successful embedding, unchanged rerun, force re-embed, dimension mismatch failure, inactive superseded vectors, and retry/dead-letter behavior.

Firecrawl Evidence:

- Use Firecrawl if JSON Schema validation, pgvector insertion/casting, batching behavior, model-server error formats, or queue-worker behavior is uncertain.

Exit Criteria:

- Chunk embeddings are persisted.
- Re-embedding is safe and repeatable.
- Failed embedding jobs do not corrupt active vectors.

## 5.6 Semantic Retrieval

Goal: return useful concept-based results over embedded chunks.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `5B. Embeddings`.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, semantic retrieval requirements.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, Story 6.2.
- `pro-merged-master-v1.2/database/070_query_examples.sql`, semantic example.
- `pro-merged-master-v1.2/docs/18_Filter_Aware_Vector_Search_Addendum.md`, vector filtering caveat.
- `contracts/api/openapi.yaml`, `SearchRequest` and `SearchResponse`.

Work:

- Embed query text through the active embedding gateway profile.
- Retrieve nearest active chunk embeddings for matching modality/dimension.
- Join semantic candidates to chunks and documents with authoritative ACL and lifecycle filters.
- Convert distances to stable semantic ranking metadata without pretending distance is a calibrated confidence score.
- Return page references and safe snippets from the matched chunk.
- Support semantic-only mode and expose debug trace only under safe development controls.
- Add tests for natural-language conceptual queries, no-vector fallback, query embedding failures, dimension mismatch, filter application, ACL exclusion, and stable result shape.

Firecrawl Evidence:

- Use Firecrawl if pgvector distance operators, HNSW query tuning, parameter casting, iterative scan behavior, or score interpretation is uncertain.

Exit Criteria:

- Conceptual search works over chunks.
- Results include matched chunk/page context.
- Semantic retrieval respects filters and ACL.

## 5.7 Filter-Aware Retrieval Planner

Goal: prevent filtered semantic search from under-returning or leaking data by planning filters deliberately.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `5C. Filter-Aware Hybrid Search`.
- `pro-merged-master-v1.2/docs/18_Filter_Aware_Vector_Search_Addendum.md`, required mitigations and hybrid flow.
- `pro-merged-master-v1.2/docs/10_Architectural_Decision_Record_Summary.md`, ADR-020.
- `pro-merged-master-v1.2/database/025_baseline_identity_acl_candidate_rules.sql`, projection columns and indexes.
- `pro-merged-master-v1.2/database/040_indexes_bm25_pgvector.sql`.
- `pro-merged-master-v1.2/database/050_views_and_functions.sql`.

Work:

- Build a query planner that chooses lexical, semantic, or hybrid candidate limits based on query mode and filters.
- Apply strong SQL predicates for household/ACL, deleted state, lifecycle, document family, date, sensitivity, folder, tags, review status, and amount filters.
- Oversample semantic candidates when filters are selective, then apply final SQL ACL/filter validation before returning results.
- Use chunk projection columns where possible to reduce expensive joins.
- Keep BM25 candidate retrieval as a parallel path for filtered search.
- Add planner trace output for tests/admin diagnostics without exposing unauthorized candidate details.
- Add tests for filtered semantic under-return cases, ACL-first final validation, folder/tag filters, date/amount filters, family/review filters, sensitivity filters, and negative visibility cases.

Firecrawl Evidence:

- Use Firecrawl for pgvector filtered nearest-neighbor behavior, HNSW tuning, iterative scans, SQL planner caveats, or ParadeDB filter interaction before changing query strategy.

Exit Criteria:

- Filters compose correctly.
- ACL and household checks are authoritative.
- Filtered semantic queries do not trivially under-return because unfiltered nearest neighbors failed filters.

## 5.8 Hybrid Fusion, RRF, And Reranker Hook

Goal: combine lexical and semantic candidates into explainable hybrid results.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `5C. Filter-Aware Hybrid Search`.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, hybrid fusion and reranking.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, hybrid fusion subphase.
- `pro-merged-master-v1.2/docs/10_Architectural_Decision_Record_Summary.md`, ADR-008.
- `pro-merged-master-v1.2/docs/18_Filter_Aware_Vector_Search_Addendum.md`, hybrid flow and result explanation.
- `pro-merged-master-v1.2/database/050_views_and_functions.sql`, `rrf_score`.
- `pro-merged-master-v1.2/database/070_query_examples.sql`, hybrid RRF example.

Work:

- Implement RRF or weighted RRF over lexical and semantic ranked lists.
- Keep lexical and semantic score scales separate; do not normalize BM25 and vector distances into one fake confidence value.
- Group candidates by document while preserving best chunk/page evidence and contributing rank sources.
- Add result explanations: matched text/field, page range, ranking sources, applied filters, lexical/semantic/field contributions, and optional reranker contribution.
- Add an optional reranker interface but leave it disabled by default unless a local profile is configured and tested.
- Add tests for RRF math, weighted fusion, duplicate document grouping, lexical-only fallback, semantic-only fallback, hybrid superiority on a small golden set, explanation shape, and disabled reranker behavior.

Firecrawl Evidence:

- Use Firecrawl if RRF weighting conventions, reranker model APIs, or ParadeDB/SQL helper behavior is uncertain.

Exit Criteria:

- Hybrid results combine lexical and semantic paths.
- Explanations are honest and useful.
- The reranker hook does not block local default search.

## 5.9 Facets, Saved Searches, And Smart Search Surfaces

Goal: make search feel like a filing cabinet by supporting persistent filters and useful facets.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `5C. Filter-Aware Hybrid Search`.
- `pro-merged-master-v1.2/docs/02_Phased_Implementation_Plan.md`, filters, facets, and saved searches.
- `pro-merged-master-v1.2/docs/04_User_Stories_and_Acceptance_Criteria.md`, saved searches and retrieval filters.
- `pro-merged-master-v1.2/database/020_core_tables.sql`, `saved_searches` and smart folder `saved_query_json`.
- `pro-merged-master-v1.2/database/050_views_and_functions.sql`, `document_summary_v`.
- `contracts/api/openapi.yaml`, folder and search schemas.

Work:

- Return facet counts for document family, folder, tag, review status, sensitivity, and date buckets where feasible.
- Ensure facet counts are computed under the same ACL and base filters as results.
- Implement saved-search persistence if not already covered by Phase 2 smart-folder work.
- Wire smart folders to saved queries without duplicating documents or bypassing ACL.
- Add tests for saved search create/update/list where applicable, smart folder query execution, facet correctness, facet ACL filtering, and active-filter preservation.

Firecrawl Evidence:

- Use Firecrawl if ParadeDB facet APIs, SQL aggregate strategy, OpenAPI design for saved searches, or accessibility patterns for faceted search controls are uncertain.

Exit Criteria:

- Users can narrow large result sets predictably.
- Facets and saved searches do not leak hidden document counts.
- Smart-folder search behavior uses the same search planner as normal search.

## 5.10 Search UI From Figma Frame 14:797

Goal: implement the user-facing search experience with filters, snippets, page references, and explanations.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, `5D. Search UI`.
- `STRUCTURA_UI_FIGMA_QA_PLAN.md`, Later UI Surfaces and workflow QA rules.
- `pro-merged-master-v1.2/design-language-v1.3.html`.
- `pro-merged-master-v1.2/docs/21_v1.3_Normalization_and_Design_Language.md`, global search and interaction principles.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, Search UX expectations.
- `contracts/api/openapi.yaml`, search schemas.
- `apps/web/src/App.tsx`.
- `apps/web/src/styles.css`.

Work:

- Use Figma frame `14:797` as the primary search surface reference.
- Keep global search persistent in the workbench top bar.
- Add the dedicated search result view with query history, instant filter chips, advanced filters, sorting, facets, snippets, page references, and result explanations.
- Preserve selected document context when filters or query mode change.
- Allow opening a result in the document Viewer and jumping to the matched page/chunk/evidence where available.
- Represent lexical, semantic, hybrid, and indexed/fresh/stale states honestly without turning machine-health details into the main content.
- Add responsive behavior: dense table/list on desktop, drawer/route inspector on narrower screens, and practical no-result states that preserve active filters.
- Add Playwright tests for lexical search, semantic search, hybrid search, advanced filters, snippets, evidence/page jump, result explanation, selected context preservation, keyboard flow, empty state, and responsive layout.

Firecrawl Evidence:

- Use Firecrawl for uncertain React/Vite patterns, WAI-ARIA combobox/filter/facet/listbox behavior, keyboard accessibility, or Playwright locator conventions.

Exit Criteria:

- Search feels like a filing cabinet, not a demo.
- Users can understand why a result matched.
- Result opening and evidence/page jump work from the UI.

## 5.11 Golden Search Benchmarks And Evaluation Hooks

Goal: measure retrieval quality before downstream analysis depends on it.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 5 gate.
- `pro-merged-master-v1.2/AGENT_START_HERE.md`, Gate D.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`, Search evaluation.
- `pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md`, search quality disappointment.
- `pro-merged-master-v1.2/docs/18_Filter_Aware_Vector_Search_Addendum.md`, evaluation requirements.
- `database/025_baseline_identity_acl_candidate_rules.sql`, `evaluation_runs`.
- `tests/`.

Work:

- Add a sanitized starter benchmark with lexical, semantic, filtered semantic, date/amount/entity/folder filters, ACL visibility, and negative cases.
- Include representative queries from the artifacts: Whole Foods bananas receipt, MRI EOB where insurance paid part, dishwasher warranty, contract amendment, return window open, claim IDs, and vehicle/tire examples where fixtures exist.
- Measure hit rate at k, mean reciprocal rank where practical, snippet usefulness metadata, and filter correctness.
- Store evaluation output in a local artifact or `evaluation_runs` without committing private corpus material.
- Add regression tests for benchmark harness behavior and fixture loading.
- Document how to run the search benchmark locally and when it is required.

Firecrawl Evidence:

- Use Firecrawl if retrieval benchmark metrics, MRR/hit-rate conventions, sanitized fixture generation, or reporting formats are uncertain.

Exit Criteria:

- Golden search queries are repeatable.
- Hybrid search can be compared against lexical-only and semantic-only.
- Quality regressions are visible before Phase 9 analysis work begins.

## 5.12 Integration, Runtime, And Observability

Goal: prove search works through the real runtime path and is observable when it fails.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 5 gate.
- `pro-merged-master-v1.2/docs/01_App_Specification.md`, performance targets.
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`, integration and E2E search tests.
- `pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv`.
- `compose.yaml`.
- `Makefile`.
- `pyproject.toml`.
- `package.json`.
- `apps/web/package.json`.

Work:

- Add API timing and safe structured logs for search mode, candidate counts, filter count, result count, and error class without logging raw full document text.
- Add service-health reporting for `worker-embeddings` and `model-embed` placeholder/real service status.
- Add runtime smoke tests for API health, upload/list/detail, parse/debug, typed extraction, embedding job, lexical search, semantic search, hybrid search, filters, and UI result open.
- Add performance guardrails aligned with the spec: common BM25 under roughly 300 ms median, semantic top-k under roughly 500 ms median on moderate local corpus, and hybrid under roughly 1 second median excluding optional heavy rerank.
- Ensure Compose search profile can run placeholders without requiring GPU model services for default tests.
- Add failure-mode coverage for missing BM25 extension, missing pgvector extension, model service down, no embeddings, stale embeddings, invalid filters, and empty corpus.

Firecrawl Evidence:

- Use Firecrawl if performance measurement conventions, Compose service behavior, ParadeDB/pgvector operational checks, or model service health APIs are uncertain.

Exit Criteria:

- Search is observable in local runtime.
- Default smoke tests do not require external inference APIs.
- Failure states are visible and actionable.

## 5.13 Contract, Static Analysis, Runtime, UI, And Gate D

Goal: prove Phase 5 is stable before analysis is exposed.

Fresh Context:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`, Phase 5 gate.
- `pro-merged-master-v1.2/AGENT_START_HERE.md`, Gate D.
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
- Run OpenAPI/schema/event contract validation, including `embed_document_job.v1.schema.json`.
- Run backend unit and integration tests.
- Run embedding worker tests, search planner tests, BM25 tests, semantic retrieval tests, hybrid fusion tests, filter tests, ACL tests, and benchmark harness tests.
- Run web build.
- Run Playwright UI workflow and screenshot validation for search frame `14:797`, advanced filters, snippets, evidence/page jump, result explanations, and responsive states.
- Run local Compose smoke where practical: API health, worker health, upload/list/detail from Phase 1, filing from Phase 2, parse/debug from Phase 3, extraction/review from Phase 4, embedding job, lexical search, semantic search, hybrid search, saved searches/facets if implemented, and search UI.
- Confirm Gate D from `AGENT_START_HERE.md`: BM25 and vector retrieval both work; hybrid fusion is visibly better on a small golden set; filters are correct and fast; highlighting/snippets are available where relevant.
- Document intentional deferrals: relationship traversal, timelines/deadlines beyond filters, difficult-document visual retrieval, multimodal reranking, analysis workspace, exports, production model optimization, and large private corpus evaluation.

Firecrawl Evidence:

- If a gate fails due to tool behavior, dependency behavior, model behavior, browser/API semantics, SQL behavior, JSON Schema behavior, search-index behavior, vector-index behavior, or security convention that is not locally obvious, use Firecrawl to find primary-source evidence before changing code.

Exit Criteria:

- Lexical, semantic, and hybrid search pass golden queries.
- ACL and filter correctness are tested.
- Snippets/highlights or safe excerpts are available where relevant.
- Gate D passes before Phase 9 analysis is exposed.

## Stop Point

Stop after Phase 5 gate validation and report:

- Files changed.
- Tests and checks run.
- Golden search benchmark summary.
- Any deferred work and the phase it belongs to.
- Any Firecrawl-sourced evidence that materially shaped implementation decisions.

Do not continue into Phase 6 without explicit user instruction.
