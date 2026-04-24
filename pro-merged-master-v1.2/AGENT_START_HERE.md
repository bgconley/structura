# Agent start here

This file is the operational contract for an implementation agent. Read it before touching the codebase.

## Primary objective

Build a local-first web application that ingests scanned or digital-native documents, preserves the original document bytes, converts them into a canonical structural representation, extracts typed data with evidence pointers, stores both raw and normalized artifacts, and makes the corpus searchable through lexical, semantic, and relational retrieval.

## Non-negotiable rules

1. The original uploaded document is the source of truth.  
   AI outputs are derivatives, never replacements.

2. Every extracted field that may be shown to the user must carry provenance.  
   The minimum provenance payload is page number plus either bounding box, table row reference, element id, or source text span.

3. Typed extraction must be schema-validated.  
   Do not persist extraction JSON as “accepted” unless it validates.

4. Low-confidence or validation-failing extraction paths must create review tasks.  
   Silent acceptance is not allowed for ambiguous or internally inconsistent results.

5. Full-text and vector search are assistive indexes, not the system of record.  
   The record remains Postgres plus object storage plus versioned extraction artifacts.

6. The implementation is local-only by default.  
   No external model API calls should be baked into critical flows.

7. The app must stay useful even when the LLM analysis layer is disabled.  
   Ingest, filing, retrieval, and review are core behavior; analysis is additive.

8. The database schema and JSON contracts in this pack are normative defaults.  
   For v1.3, the normalized source of truth is `docs/10_Architectural_Decision_Record_Summary.md`, `docs/21_v1.3_Normalization_and_Design_Language.md`, `docs/19_v1.2_Normalization_and_Source_of_Truth.md`, `database/`, and `contracts/`.

9. All model outputs stored in the system must be versioned.  
   Model name, model version, prompt version, and extraction schema version must be persisted.

10. Do not “simplify” away evidence, review state, or canonical artifacts in the name of speed.  
    Those are foundational, not optional.

## Execution order

1. Read `docs/01_App_Specification.md`
2. Read `docs/02_Phased_Implementation_Plan.md`
3. Read `docs/10_Architectural_Decision_Record_Summary.md`
4. Read `docs/21_v1.3_Normalization_and_Design_Language.md`
5. Read `docs/19_v1.2_Normalization_and_Source_of_Truth.md`
6. Read `docs/11_Model_Routing_and_Output_Contracts.md`
7. Stand up infrastructure from `docs/08_ZFS_Datasets_and_Storage_Plan.md` and `docs/09_Deployment_and_Runtime_Architecture.md`
8. Apply SQL files in `database/` in order
9. Scaffold the repository exactly or very closely to `docs/07_Repository_Layout_and_Coding_Standards.md`
10. Implement bootstrap admin creation plus `POST/GET/DELETE /api/v1/auth/session` before exposing document routes beyond local dev stubs
11. Implement phases in order; do not skip the stop/go gates
12. Validate against `docs/04_User_Stories_and_Acceptance_Criteria.md`
13. Pass the quality gates in `docs/05_*.md` and `docs/06_*.md`

## First implementation milestone

Before any multimodal extraction work begins, the system must be able to do all of the following:

- Bootstrap the first local admin and create a durable session
- Enforce auth on document and asset routes
- Accept document upload
- Save the original artifact immutably
- Compute and persist fingerprints
- Create a document record and an original asset record
- Render page thumbnails for browsing
- Display the original document in a clean viewer
- Persist job state and surface worker health
- Show the document in an inbox

If this baseline is not clean and observable, stop and fix it before integrating Docling or any VLM.

## Second implementation milestone

Before hybrid search work begins, the system must be able to do all of the following:

- Convert at least PDF input into Docling JSON
- Persist pages, elements, chunks, and raw structural artifacts
- Show extracted text and page-level evidence in the UI
- Record extraction runs and their status
- Open review tasks for failed validations
- Re-run extraction idempotently without losing history

## Third implementation milestone

Before user-facing “analysis chat” exists, the system must already support:

- Accurate document search by BM25
- Useful semantic search across chunks
- Clean filtering by type, date, folder, tags, and review status
- Structured viewing of receipt, invoice, and EOB extractions
- Manual correction flows with audit trails
- Related-document navigation

Do not expose a conversational interface early and let it mask foundational product gaps.

## Implementation style

- Prefer boring, inspectable building blocks.
- Keep the monorepo legible.
- Use explicit contracts.
- Use migrations instead of ad hoc database changes.
- Make every background pipeline step retryable and idempotent.
- Store enough metadata to debug an extraction weeks later.

## Stop/go gates

### Gate A - ingest baseline
Go only if:
- Upload works
- Original bytes are preserved
- Document appears in inbox
- Thumbnail generation works
- Job records are visible
- No orphaned assets or rows are created on partial failure

### Gate B - canonical parse baseline
Go only if:
- Docling conversion produces persisted canonical artifacts
- Page and chunk rows are created correctly
- Viewer can highlight source evidence
- Reprocessing supersedes old extraction state safely

### Gate C - typed extraction baseline
Go only if:
- Receipt, invoice, and EOB schemas validate
- At least arithmetic checks and missing-required-field checks exist
- Review tasks are generated automatically
- Manual corrections are persisted and auditable

### Gate D - retrieval baseline
Go only if:
- BM25 and vector retrieval both work
- Hybrid fusion produces visibly better results on a small golden set
- Search filters are correct and fast
- Highlighting/snippets are available where relevant

### Gate E - analysis baseline
Go only if:
- Analysis outputs cite source documents and page references
- Analysis can be disabled without breaking normal usage
- No analysis output overwrites accepted extraction data without explicit user action

## Deliverable philosophy

Prefer an honest, incremental, well-instrumented system over a broad but opaque one. If a feature cannot yet be trusted, surface it as suggested or review-required rather than pretending it is final.


## v1.3 normalization note

The v1.1 addendum documents are now background rationale, not competing defaults.
The v1.2 normalization document remains historical source-of-truth cleanup; `docs/21_v1.3_Normalization_and_Design_Language.md` is the current normalization layer.

For implementation, treat these files as normative:

1. `docs/10_Architectural_Decision_Record_Summary.md`
2. `docs/21_v1.3_Normalization_and_Design_Language.md`
3. `docs/19_v1.2_Normalization_and_Source_of_Truth.md`
4. `database/001_extensions.sql`
5. `database/010_types_and_enums.sql`
6. `database/020_core_tables.sql`
7. `database/025_baseline_identity_acl_candidate_rules.sql`
8. `database/030_constraints_and_triggers.sql`
9. `database/040_indexes_bm25_pgvector.sql`
10. `database/050_views_and_functions.sql`
11. `contracts/api/openapi.yaml`

Read docs 13 through 20 for rationale and historical context, but do not treat them as equally authoritative alternatives.
