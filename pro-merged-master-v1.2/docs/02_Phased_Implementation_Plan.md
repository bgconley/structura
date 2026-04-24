# Phased implementation plan

Version: v1.3 planning baseline  
Prepared: 2026-04-23

## 1. How to use this plan

This plan is written for an implementation agent or engineering team that needs a concrete order of operations, clear dependencies, and explicit done criteria. The phases are intentionally structured to prevent the common failure mode of building an impressive-looking AI interface on top of weak ingestion, weak provenance, or weak storage discipline.

Each phase includes:

- objective
- why it exists
- subphases
- prerequisites
- major implementation tasks
- expected deliverables
- test and verification criteria
- stop/go gate

Follow the phases in order. Parallel work is allowed where noted, but do not skip the stop/go gates.

## 2. Delivery principles

- Build from durable storage outward.
- Make the simplest trustworthy thing work before layering intelligence.
- Do not introduce multimodal extraction before the canonical parse layer is stable.
- Do not introduce LLM analysis before reviewable structured extraction and strong search exist.
- Every asynchronous stage must be idempotent and observable.
- Every schema must be versioned.
- Every model output that influences user trust must be inspectable.

## 3. Phase 0 - foundation and skeleton

### Objective

Create the repository, runtime shell, local infrastructure, configuration model, and operational guardrails required for all later work.

### Why this phase exists

Without a clean repo structure, migration story, config strategy, and worker orchestration pattern, later phases become brittle and hard to debug.

### Prerequisites

- none

### Subphase 0A - repository and coding standards

Implement:

- monorepo scaffold
- linting and formatting
- Python environment tooling
- TypeScript toolchain
- shared configuration package
- `.env` strategy and secret-loading policy
- migration tooling choice
- API versioning baseline
- JSON Schema storage location
- shared domain types package if desired

Deliverables:

- repo directories created
- README for local development
- pre-commit or equivalent tooling
- CI baseline for lint plus unit tests
- initial ADR file stating architecture defaults

Done criteria:

- any new engineer or agent can clone and run `make bootstrap` or equivalent
- a minimal frontend and backend health route work
- DB migration tooling is wired, even if no app tables exist yet

### Subphase 0B - infrastructure bootstrap

Implement:

- Docker Compose file or files
- Postgres service with `pg_search` and `pgvector`
- queue transport profile configuration (PGMQ default; Redis fallback only if required)
- reverse proxy or direct service exposure strategy
- model-serving container placeholders
- persistent bind mounts pointing to the planned ZFS dataset layout
- health checks and restart policies
- backup / snapshot notes

Deliverables:

- working `docker compose up`
- healthy containers
- persistent storage mounts
- documented port map

Done criteria:

- services restart cleanly
- DB persists data across restart
- `pg_search` and `pgvector` can be created in the database
- health dashboards or logs are reachable

### Subphase 0C - database baseline

Implement:

- run the SQL files in `database/`
- confirm schema creation
- create migration wrapper around the SQL baseline
- add initial seed taxonomies
- add DB smoke tests

Deliverables:

- empty but queryable application schema
- seeded folders and tags
- migrations committed

Done criteria:

- schema applies from scratch to a blank DB
- schema can be torn down and reapplied cleanly
- sample inserts across core tables work

### Subphase 0D - operational baseline

Implement:

- structured logging
- request correlation ids
- background job status model
- worker heartbeat or liveness signals
- metrics placeholders
- error reporting strategy that does not leak document content

Deliverables:

- logs are readable
- job rows update consistently
- API and workers expose health

### Subphase 0E - auth and session foundation

Implement:

- bootstrap admin creation flow
- password credential storage using Argon2id or an equivalent strong one-way hash
- DB-backed session create/current/delete routes aligned to the OpenAPI contract
- secure session cookie configuration for browser use
- CSRF protection for browser mutating routes
- protected-route middleware conventions for document and asset routes
- API token parsing stub for future automation flows

Deliverables:

- working auth/session endpoints
- auth smoke tests
- protected API skeleton

Done criteria:

- a first local admin can sign in and fetch the current session
- anonymous access to protected document routes is rejected by default
- session `auth_method` is persisted durably
- bootstrap passwords can be flagged for rotation or disabled later

### Phase 0 stop/go gate

Proceed only when:

- the monorepo is stable;
- local infrastructure boots without manual heroics;
- the DB schema applies cleanly;
- job state is observable;
- auth/session baseline works;
- bind mounts align to the ZFS plan.

## 4. Phase 1 - ingest, original preservation, and basic browsing

### Objective

Create the minimum trustworthy filing cabinet: upload a document, preserve it immutably, show it in an inbox, and browse the source artifact.

### Why this phase exists

If the system cannot preserve originals and make them easy to browse, none of the AI layers matter.

### Prerequisites

- Phase 0 complete

### Subphase 1A - object storage abstraction

Implement:

- content-addressed storage interface
- filesystem backend using the planned canonical, derived, and export ZFS object roots
- object URI schema
- SHA-256 hashing
- file metadata capture
- dedupe signal generation without destructive merging

Deliverables:

- storage service package
- object write, read, and existence functions
- canonical pathing scheme

Done criteria:

- original files are stored under deterministic content-based locations
- files can be retrieved by asset row id
- duplicate detection based on exact bytes works

### Subphase 1B - upload API and job kickoff

Implement:

- authenticated multipart upload endpoint
- document row creation
- original asset row creation
- ingest batch support for bulk uploads
- initial pipeline job creation
- basic validation of MIME type and size
- optimistic inbox appearance

Deliverables:

- POST document upload route
- upload service tests
- job kickoff logic

Done criteria:

- a document is visible in the inbox immediately after upload
- source metadata is persisted
- upload requires a valid session or API token
- partial failures do not leave dangling rows or files

### Subphase 1C - previews and viewer

Implement:

- PDF preview generation
- thumbnail creation
- page image generation cache policy
- document detail page with viewer
- thumbnails sidebar
- inbox list
- document status badges

Deliverables:

- working inbox page
- working document detail page
- page preview artifacts

Done criteria:

- a user can upload and visually inspect a document end-to-end
- the system clearly shows processing state
- a failed preview job is visible and retryable

### Subphase 1D - manual filing baseline

Implement:

- create folders
- create tags
- assign folder memberships
- assign tags
- add notes
- basic metadata editing such as title and document date

Deliverables:

- folder and tag UI
- document edit actions
- folder tree view

Done criteria:

- the app already works as a manual filing cabinet before AI extraction exists

### Phase 1 stop/go gate

Proceed only when:

- original bytes are preserved immutably;
- upload is stable;
- inbox and viewer are pleasant to use;
- manual foldering and tagging work;
- no data corruption occurs during retries or restarts.

## 5. Phase 2 - canonical parsing with Docling

### Objective

Introduce a durable, inspectable structural representation for each document.

### Why this phase exists

Canonical parsing is the bridge between raw files and trustworthy structured extraction. It is the layer that makes later model changes survivable.

### Prerequisites

- Phase 1 complete

### Subphase 2A - Docling worker integration

Implement:

- worker that consumes convert jobs
- Docling conversion for PDFs and images
- raw artifact persistence: JSON, markdown, optional HTML
- conversion metadata capture
- retry and timeout policy
- explicit failure states

Deliverables:

- Docling worker container
- conversion orchestration service
- persisted canonical artifacts

Done criteria:

- a converted document always stores raw canonical artifacts or an explicit failed status
- conversion is idempotent
- rerunning conversion supersedes the “current” canonical artifact without losing history

### Subphase 2B - database population from canonical artifacts

Implement:

- page row creation
- element row creation
- chunk generation strategy
- table row / artifact creation
- page text persistence
- page geometry metadata
- provenance linkage back to canonical artifact ids

Deliverables:

- canonical-to-relational ingestion code
- chunking logic
- table extraction persistence

Done criteria:

- DB rows for pages, elements, chunks, and tables match the source artifact structure closely enough for later evidence jumps

### Subphase 2C - canonical debug tooling

Implement:

- debug panel in document detail view
- raw Docling artifact viewer
- element overlay or at least element list
- chunk preview
- table preview
- job run history for the document

Deliverables:

- internal debug tabs
- QA workflow for inspecting parse outputs

Done criteria:

- an engineer can inspect how the system understood a page before any schema-specific extraction happens

### Subphase 2D - parse quality heuristics

Implement:

- digital-native vs scanned heuristic
- OCR confidence tracking
- handwriting suspicion signals
- page complexity signals
- parse-quality flags that can influence routing later

Deliverables:

- metadata enrichment stored on document and page rows

### Phase 2 stop/go gate

Proceed only when:

- canonical parse artifacts are durable;
- pages, chunks, and tables are stored coherently;
- the UI can expose parse internals;
- parse failure is explicit and reviewable.

## 6. Phase 3 - classification, structured extraction, and review workflow

### Objective

Turn parsed documents into validated structured records with human-correctable review flows.

### Why this phase exists

This is where the application stops being merely a document browser and becomes an intelligent filing cabinet.

### Prerequisites

- Phase 2 complete

### Subphase 3A - document family classification

Implement:

- classification service
- heuristic signals from filename, sender, parse structure, and existing entities
- model-assisted classifier where helpful
- persistence of family, subtype, confidence, and rationale metadata
- user override flow

Deliverables:

- classifier module
- classification endpoint or job
- UI to show and override family

Done criteria:

- the majority of common document families are classified into useful buckets
- misclassified documents can be corrected without breaking downstream history

### Subphase 3B - extraction contracts and validators

Implement:

- JSON Schemas from `contracts/schemas`
- Pydantic equivalents in backend code
- validator service
- arithmetic validation rules
- missing-required-field checks
- cross-field consistency checks

Deliverables:

- validation package
- schema registry
- test fixtures per document family

Done criteria:

- malformed extraction cannot be marked accepted
- validation errors are structured and machine-readable

### Subphase 3C - model routing and extraction workers

Implement:

- extraction orchestrator
- Docling-only path where possible
- Granite route for table/KVP-heavy forms
- Qwen route for harder visual reasoning and handwriting
- raw output capture
- normalized output persistence
- model metadata capture

Deliverables:

- extraction jobs
- model gateway abstraction
- persisted extraction runs

Done criteria:

- receipt, invoice, and EOB extraction run end-to-end against real samples
- raw and normalized outputs are both stored

### Subphase 3D - evidence linking

Implement:

- evidence object format
- mapping from extracted fields to pages plus boxes, elements, table rows, source text spans, or source text excerpts
- UI field-to-source highlight interactions
- evidence persistence in normalized rows

Deliverables:

- evidence resolver
- field click-to-highlight UI

Done criteria:

- a user can click a value and see where it came from
- trusted extracted values have page number plus at least one concrete locator

### Subphase 3E - review queue and correction system

Implement:

- review task generation
- review inbox UI
- accept / reject / correct actions
- correction audit events
- re-extraction triggers
- superseding accepted values safely

Deliverables:

- review queue page
- field correction flow
- audit log entries

Done criteria:

- extraction quality is no longer opaque; it is a managed workflow

### Phase 3 stop/go gate

Proceed only when:

- at least three important schemas work end-to-end;
- evidence is visible;
- review tasks are generated automatically;
- corrections are auditable and do not overwrite history invisibly.

## 7. Phase 4 - lexical, semantic, and hybrid retrieval

### Objective

Make the corpus truly retrievable through fast, precise, and semantically helpful search.

### Why this phase exists

Users do not remember filenames and paths. Search quality is central to the product.

### Prerequisites

- Phase 3 complete

### Subphase 4A - BM25 indexing with ParadeDB

Implement:

- BM25 indexes from the provided SQL
- search endpoints over documents and chunks
- lexical snippets or highlights
- relevance sort
- basic facets
- search result grouping

Deliverables:

- search API v1
- lexical search UI
- result cards with snippets

Done criteria:

- exact term and phrase-heavy searches are good enough to trust
- query latency is acceptable on a starter corpus

### Subphase 4B - text embeddings and vector retrieval

Implement:

- embedding worker
- chunk embedding generation
- document embedding generation where useful
- pgvector storage
- top-k semantic retrieval endpoint
- idempotent re-embedding strategy

Deliverables:

- embedding service
- semantic search path
- model metadata persisted with vectors

Done criteria:

- concept-based retrieval works on realistic queries even when exact keywords are missing

### Subphase 4C - hybrid fusion and reranking

Implement:

- candidate generation from BM25 and vector retrieval
- RRF or weighted RRF implementation
- optional reranking hook
- final result blending
- explanation of why a result matched

Deliverables:

- hybrid search endpoint
- fusion helper
- evaluation notebook or script against a small golden set

Done criteria:

- hybrid results are visibly better than either lexical or semantic alone on the chosen benchmark queries

### Subphase 4D - filters, facets, and saved searches

Implement:

- filter grammar for date, amount, family, folder, tag, review status, deadline presence, relationship presence
- saved search persistence
- smart folders based on saved searches
- facet counts

Deliverables:

- advanced search UI
- saved search model
- smart folder surface

Done criteria:

- retrieval feels like a real filing cabinet, not only an AI demo

### Phase 4 stop/go gate

Proceed only when:

- lexical, semantic, and hybrid retrieval are all operational;
- filters and facets are correct;
- result quality has been measured on real examples.

## 8. Phase 5 - organization intelligence and related documents

### Objective

Add graph-like organization, timelines, reminders, and missing-companion-document logic.

### Why this phase exists

The product becomes much more useful when it understands that documents belong to cases, transactions, claims, or object histories.

### Prerequisites

- Phase 4 complete

### Subphase 5A - relationship model and UI

Implement:

- relationship creation API
- relationship suggestion engine
- timeline view
- related-document panel

Deliverables:

- relationship table fully used in app
- related-document browsing flow

Done criteria:

- users can navigate from invoice to receipt to warranty to service history, or from bill to EOB to payment

### Subphase 5B - entities and document-centric timelines

Implement:

- basic party resolution
- provider / merchant / insurer profile pages
- entity-centric document listing
- timeline grouping by entity and date

Deliverables:

- party resolution background job or service
- entity view pages

### Subphase 5C - deadlines and reminders

Implement:

- due date / renewal / expiration extraction surfacing
- open deadlines view
- reminder heuristics
- smart folders such as “warranties expiring soon” or “unmatched medical documents”

Deliverables:

- deadlines page
- reminder widgets

### Phase 5 stop/go gate

Proceed only when:

- relationships feel useful rather than decorative;
- at least a few high-value smart views exist;
- users can traverse meaningful document history.

## 9. Phase 6 - visual retrieval and difficult document handling

### Objective

Improve the system’s performance on degraded scans, layout-sensitive retrieval, and handwriting-heavy material.

### Why this phase exists

Some document retrieval and understanding problems are not text-only.

### Prerequisites

- Phase 4 complete
- Phase 5 optional but recommended

### Subphase 6A - selective visual embedding

Implement:

- policy for when to embed page visuals
- page-level or crop-level visual embeddings
- storage and indexing in `embeddings`
- visual retrieval endpoint
- mixed result blending

Deliverables:

- visual embedding worker path
- UI toggles or automatic inclusion in general search

### Subphase 6B - handwriting-specific routing

Implement:

- stronger handwriting detection
- Qwen-heavy route for transcription
- confidence-aware review defaults
- handwriting-focused UI cues

Deliverables:

- handwriting pipeline variant
- review-first behavior for low-confidence transcriptions

### Subphase 6C - search quality tuning for low-text pages

Implement:

- indexing adjustments for sparse or noisy text
- layout-sensitive retrieval options
- optional multimodal reranker for difficult result sets

Deliverables:

- benchmark queries targeting scans, notes, and low-text pages

### Phase 6 stop/go gate

Proceed only when:

- difficult documents are no longer second-class citizens;
- the app clearly marks uncertainty on handwritten or visually degraded material.

## 10. Phase 7 - optional analysis workspace

### Objective

Layer in bounded, source-cited analysis capabilities without turning the product into a chatbot-shaped interface.

### Why this phase exists

The user wants optional analytical help, but only after the filing system itself is strong.

### Prerequisites

- Phase 4 complete
- Phase 3 review system complete

### Subphase 7A - analysis run model

Implement:

- analysis request objects
- selected document scopes
- analysis note storage
- citation model
- model metadata and prompt version persistence

Deliverables:

- analysis run API
- persisted analysis notes

### Subphase 7B - core analysis actions

Implement:

- summarize
- compare
- explain
- extract obligations and deadlines
- tax-relevant scan
- medical explanation

Deliverables:

- analysis workspace UI
- citation-backed result view

### Subphase 7C - safety boundaries

Implement:

- explicit distinction between extracted fact and analysis opinion
- analysis note does not overwrite extracted records
- visible disclaimer language where uncertainty exists
- user control over whether analysis is saved

Deliverables:

- clean boundary between filing system and analysis layer

### Phase 7 stop/go gate

Proceed only when:

- analysis outputs always cite sources;
- analysis can be disabled without breaking core product behavior.

## 11. Phase 8 - security, backups, and operational hardening

### Objective

Make the system durable, supportable, and safe for everyday use.

### Why this phase exists

Sensitive document stores should not rely on “I will fix that later” security or backup plans.

### Prerequisites

- core functional phases complete enough to justify hardening

### Subphase 8A - auth hardening and access audits

Implement:

- passkey or WebAuthn enrollment if not already enabled
- magic-link recovery and invite hardening
- session timeout, rotation, and revoke-all controls
- API token lifecycle management
- asset authorization audits and household/ACL regression tests

Deliverables:

- auth hardening settings surfaces
- authorization regression coverage
- hardened recovery and token flows

### Subphase 8B - backup and restore

Implement:

- Postgres backup scripts or procedures
- ZFS snapshot schedule
- object store consistency checks
- restore test procedure
- export and disaster recovery notes

Deliverables:

- documented restore runbook
- restore test evidence

### Subphase 8C - observability and admin surfaces

Implement:

- admin jobs page
- failed-job retry tools
- storage usage panel
- model-server health panel
- extraction failure statistics

Deliverables:

- admin / ops UI
- metrics dashboards or at least structured status endpoints

### Phase 8 stop/go gate

Proceed only when:

- restore has been tested;
- auth hardening matches the intended exposure model;
- operational visibility is sufficient for self-hosting.

## 12. Phase 9 - benchmark corpus, regression discipline, and release candidate

### Objective

Move from “it seems to work” to “we can measure and trust it.”

### Why this phase exists

Document AI systems regress quietly unless they are evaluated against fixed corpora and gold answers.

### Prerequisites

- functional features substantially complete

### Subphase 9A - golden corpus assembly

Create a representative set of documents including:

- clean digital invoices
- ugly scanned receipts
- medical EOBs
- legal notices
- warranties
- handwritten notes
- long PDF reference documents

For each sample, preserve:

- original artifact
- expected classification
- expected extracted key fields
- search queries that should retrieve it
- edge cases and known ambiguities

### Subphase 9B - automated evaluation

Implement:

- field-level extraction scoring where possible
- search benchmark queries with expected top-k matches
- UI smoke tests
- migration-from-scratch tests
- restore tests

### Subphase 9C - release candidate checklist

Require:

- passing migration tests
- passing golden search tests
- acceptable extraction metrics
- successful restore rehearsal
- known-issue list documented
- no critical data-integrity bugs outstanding

## 13. Cross-phase workstreams

Some workstreams should exist throughout multiple phases.

### 13.1 Prompt and schema discipline
Every extraction or analysis prompt should be versioned, checked in, and associated with schema versions.

### 13.2 Evaluation discipline
As soon as the first few document families work, start building the golden corpus. Do not wait until the end.

### 13.3 UX discipline
Do not leave the UI rough until “later.” Review and search quality are strongly affected by presentation and evidence affordances.

### 13.4 Migration discipline
All schema changes should be migration-backed and rollback-considered.

### 13.5 Security discipline
Do not postpone secret handling, route protection, or backup design to the very end.

## 14. Recommended branch and work cadence for an agentic coder

- One phase or subphase per pull request where possible
- Keep migrations separate from heavy application changes if practical
- Add or update tests in the same change set as the feature
- Update ADR summary when deviating from baseline design
- Keep JSON Schema contracts and backend models synchronized

## 15. Definition of done for the project’s first real usable release

The first genuinely usable release is complete when:

- documents can be uploaded, stored, and browsed;
- Docling canonical parsing is durable and visible;
- receipt, invoice, and EOB extraction are functional with review flows;
- hybrid search is good on a curated golden set;
- folders, tags, smart folders, and related documents work;
- backups and restore have been rehearsed;
- analysis is optional, cited, and bounded.

## 16. Final instruction to the implementation agent

If schedule pressure emerges, cut breadth before cutting provenance, validation, review, or original-asset integrity. Those are the foundations that make the whole application worth using.
