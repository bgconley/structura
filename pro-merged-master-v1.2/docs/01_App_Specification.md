# App specification

Version: v1.3 planning baseline  
Prepared: 2026-04-23

## 1. Product summary

The application is a local-first document intelligence and filing cabinet system for personal or household records. Its primary job is to ingest physical or digital-native documents, preserve the original files immutably, derive a canonical structural representation, extract typed facts with evidence, and make the resulting corpus easy to file, search, review, and understand.

The product is not a generic chatbot with a PDF upload feature. It is a durable system of record with explicit provenance, explicit review state, and explicit versioning of all derived artifacts. Its design center is trustworthiness and retrieval quality, not marketing-style automation.

The intended experience is this:

- a user receives a digital invoice, a scanned receipt, a medical EOB, a legal letter, or a handwritten note;
- the user uploads the PDF or image-derived PDF to the application;
- the system stores the original document bytes, fingerprints the file, creates a document record, and queues background processing;
- Docling converts the document into a canonical structural artifact and exports text, layout, hierarchy, and table signals;
- targeted VLM extraction workers convert the document into typed JSON using document-family-specific schemas;
- the system validates the extraction, generates review tasks if needed, stores both raw and normalized artifacts, embeds search-ready content, and indexes the corpus;
- the user can now browse, file, search, filter, relate, and optionally analyze the document set.

## 2. Goals

### 2.1 Primary goals

- Preserve documents in full fidelity and immutably.
- Produce a reliable canonical representation that can survive model swaps.
- Extract high-value structured data from common household document families.
- Make retrieval excellent through lexical, semantic, and relational search.
- Keep the filing experience intuitive with folders, tags, smart folders, and related-document views.
- Make every AI-derived value inspectable by linking it back to evidence.
- Allow optional higher-level analysis without forcing the user into an LLM-first workflow.
- Operate entirely on premises by default.

### 2.2 Secondary goals

- Support batch ingestion and backlog cleanup.
- Provide a durable review queue so extraction quality improves over time.
- Accumulate corrected examples that can later support fine-tuning or prompt optimization.
- Offer export flows for records requests, taxes, reimbursements, claims, or legal preparation.
- Be extensible enough to add more document families without rewriting the core.

### 2.3 Non-goals for v1

- General multi-tenant SaaS deployment.
- Public cloud dependence.
- OCR for arbitrary photo albums or non-document image libraries.
- Full legal or medical expert system behavior.
- Automatic destruction of source files after extraction.
- Autonomous filing with zero user oversight for high-sensitivity documents.
- Fine-tuning at project start.

## 3. Personas and usage contexts

### 3.1 Primary persona: meticulous household operator

A technically capable user wants a single local system for receipts, invoices, warranties, tax-relevant records, vehicle records, insurance documents, medical bills, and legal paperwork. They care about search precision, provenance, and data durability.

### 3.2 Secondary persona: family archivist

A user is scanning years of paper records and needs batch ingest, duplicate detection, strong foldering, and document relationships such as invoice plus warranty plus receipt plus service history.

### 3.3 Secondary persona: incident responder for life paperwork

A user needs to answer questions quickly under stress:

- “What did insurance pay for this procedure?”
- “Where is the warranty for the dishwasher?”
- “What was the tire replacement receipt?”
- “Show me every document related to claim X.”
- “What documents are relevant for this year’s taxes?”

The system must support these tasks without requiring the user to remember exact filenames or folder paths.

## 4. Platform constraints and environmental assumptions

### 4.1 Host assumptions

- Host OS: Ubuntu 24.04
- Hardware: Lenovo P620 with AMD Threadripper Pro 3975WX, 128 GB RAM
- GPU: 2 x NVIDIA RTX Pro 4000 Blackwell, 24 GB each
- Storage: ZFS zpool with mirrored vdev layout and roughly 3.3 TB usable capacity
- Container runtime: Docker available
- Orchestration preference: Docker Compose first, k3s optional later

### 4.2 Deployment assumptions

- The application is expected to run primarily on a single node.
- Local LAN or VPN access may be allowed later, but public internet exposure is not assumed.
- The system should not require internet access during normal operation after models and dependencies are installed.
- Large model files should live on dedicated ZFS datasets and should not be mixed with object storage or database files.

### 4.3 Operational constraints

- The application must degrade gracefully if the analysis LLM is disabled.
- Model-serving workloads and DB workloads share one box, so resource isolation matters.
- The system should be able to process a backlog asynchronously without blocking normal browsing and search.
- Schema, job state, and source artifacts must be resilient to restarts.

## 5. Core product principles

### 5.1 Original-first

The original PDF or scanned artifact is immutable and authoritative.

### 5.2 Evidence-backed extraction

Every user-visible extracted value must be traceable to pages, regions, rows, or source text spans.

### 5.3 Canonical representation before specialization

Docling’s canonical structural artifact is the stable middle layer. Model-specific outputs are important but should not be the only durable representation.

### 5.4 Hybrid retrieval by default

The system should combine BM25, semantic similarity, relational filters, and document relationships. No one retrieval mode is sufficient by itself.

### 5.5 Optional analysis, not mandatory chat

The app must remain excellent as a filing cabinet and search system even when no LLM analysis is used.

### 5.6 Reviewability over false confidence

When extraction quality is uncertain, the system should raise review tasks instead of silently persisting brittle facts as trusted.

## 6. Functional requirements

## 6.1 Ingestion

The system shall support the following ingestion sources:

- direct browser upload of PDFs and image files
- drag-and-drop upload
- watched-folder ingestion for bulk import
- mobile-scanned PDFs exported from iOS scanning apps
- email attachment import in a later phase
- ZIP-based bulk import in a later phase

The system shall, at ingest time:

- create a document record immediately;
- compute a SHA-256 fingerprint of the original bytes;
- record source metadata such as original filename, MIME type, byte size, source channel, and received timestamp;
- preserve the original artifact immutably;
- create a pipeline job chain without blocking the UI;
- detect likely duplicates based on file hash and later based on structural similarity;
- create thumbnails and page previews quickly enough that the user sees progress.

The system shall not:

- overwrite an existing original asset;
- lose the link between the document row and the original artifact;
- require AI processing to finish before the document appears in the inbox.

## 6.2 Classification

The system shall assign each document a document family and subtype. Classification may begin with heuristic plus model-assisted classification. A classification result must include:

- primary family
- optional subtype
- confidence
- source engine
- model name / version where relevant
- rationale metadata or signals
- review status

Initial document families should include at least:

- receipt
- invoice
- medical EOB
- medical bill
- insurance document
- legal contract
- legal notice / correspondence
- tax document
- warranty
- identity document
- bank / financial statement
- handwritten note
- typed note
- white paper / reference document
- generic untyped document

The classifier must allow later reclassification by the user without damaging source artifacts.

## 6.3 Canonical parse

Every ingestible document must be convertible into a canonical representation. For v1, the required canonical artifacts are:

- original artifact
- page images or renderable page previews
- Docling JSON
- search-oriented text or markdown export
- extraction run metadata
- page and element rows in Postgres

The canonical parse layer must expose at least:

- document hierarchy
- pages
- reading order
- bounding boxes where available
- tables
- headers and footers where available
- provenance for extracted elements

If a document cannot be parsed into a strong canonical representation, the system shall still preserve the original, store failure metadata, and present the document to the user as an unparsed artifact that may need manual handling.

## 6.4 Typed extraction

The system shall perform structured extraction into document-family-specific JSON schemas. V1 required schemas are:

- receipt
- invoice
- medical EOB
- document classification
- review action
- analysis note

Typed extraction rules:

- outputs must validate against JSON Schema or Pydantic-derived schema definitions;
- every trusted extracted field must include confidence and evidence with a concrete source locator;
- raw model output and normalized extraction must both be stored;
- arithmetic and consistency checks must run after extraction;
- invalid or low-confidence results must generate review tasks.

Examples of high-value structured extraction requirements:

### Receipt
- merchant name
- merchant address if present
- transaction date and time
- subtotal
- tax
- total
- payment hint
- line items with quantity, unit, unit price, and amount where present

### Invoice
- seller
- buyer
- invoice number
- issue date
- due date
- purchase order number if present
- totals
- remittance information
- line items and per-line amounts

### Medical EOB
- payer
- patient
- provider
- claim number
- processed date
- service lines
- procedure code and modifiers where present
- billed amount
- allowed amount
- plan paid
- patient responsibility
- deductible / coinsurance / copay where visible

## 6.5 Filing and organization

The system shall support both manual and derived organization.

### Manual organization
- nested folders with a tree view
- tags
- notes
- “primary folder” hint for users who want a single dominant location

### Derived organization
- smart folders based on saved searches and filters
- related-document links
- timelines for related documents
- entity-centric browsing by merchant, provider, insurer, vehicle, home appliance, or topic

The system shall not require one physical document to live in exactly one folder. Folder membership is a user-facing organization feature, not the storage primitive.

## 6.6 Search and retrieval

The search system shall combine the following retrieval modes:

- BM25 lexical search via ParadeDB
- semantic text retrieval via pgvector
- optional visual or page-level multimodal retrieval
- relational filtering by metadata, folders, tags, dates, and amounts
- reranking for top candidates
- relationship traversal across linked documents

The UI must support:

- global search bar
- advanced filters
- faceted navigation
- highlighted lexical matches where useful
- grouped results by document family or folder
- quick actions from results
- result snippets and page references

Representative supported queries:

- “MRI bill from January where insurance paid only part”
- “Whole Foods receipt with bananas”
- “dishwasher warranty”
- “return window still open”
- “Docusign contract amendment”
- “medical documents for claim ABC123”
- “vehicle tire replacement around March”

## 6.7 Review and correction

The system shall include a first-class review workflow. Review tasks may be created for:

- low extraction confidence
- arithmetic mismatch
- missing required fields
- duplicate suspicion
- uncertain classification
- relationship suggestions that need confirmation
- handwriting-heavy documents
- PII redaction or sharing preparation

A reviewer must be able to:

- open the source document and side-by-side extracted fields
- click a field and jump to evidence
- edit a field
- accept or reject a field
- reclassify the document
- mark the document as reviewed
- leave notes
- trigger re-extraction if the schema or prompt changed

All corrections must be auditable.

## 6.8 Related documents and timelines

The system shall support explicit relationships between documents. Core relationship types include:

- duplicate_of
- invoice_for
- receipt_for
- eob_for
- bill_for
- amendment_to
- renewal_of
- attachment_to
- warranty_for
- proof_of_payment_for

Relationship suggestions may be model-assisted but must be confirmable by the user.

The UI should expose:

- related document side panel
- timeline view
- grouped transaction or case view
- “missing companion document” suggestions in later phases

## 6.9 Optional analysis workspace

The analysis workspace is opt-in. It is separate from ordinary filing and retrieval. It allows a user to select one or more documents and ask for:

- explanation
- comparison
- summarization
- timeline extraction
- obligation or deadline scan
- tax-relevant expense extraction
- medical explanation in plain English

Analysis outputs must:

- cite source documents and pages;
- be persisted separately from canonical extraction;
- never silently mutate accepted extraction data;
- carry model version, prompt version, and timestamp.

## 6.10 Export and sharing

The system shall support exporting:

- originals only
- originals plus extracted JSON
- originals plus CSV / JSONL of normalized data
- redacted sharing bundles in later phases
- evidence-backed review reports in later phases

Export bundles should include a manifest describing included files and provenance.

## 7. Non-functional requirements

## 7.1 Correctness

- The system must prefer explicit validation failure over hidden corruption.
- Idempotent reprocessing is required.
- A failed worker must not orphan half-written state without detectability.
- Schema migrations must be versioned.

## 7.2 Performance

Baseline v1 targets on the described workstation:

- upload acknowledgement: user sees document row within 2 seconds of upload completion
- inbox listing: under 500 ms for common views on moderate corpus sizes
- document open: first page visible within 1 second after cached preview exists
- BM25 search: under 300 ms median for common lexical queries on moderate corpus sizes
- semantic search: under 500 ms median for top-k retrieval on moderate corpus sizes
- hybrid search endpoint: under 1 second median including fusion, excluding optional heavy rerank
- extraction throughput: asynchronous; user-facing latency is less important than observability and quality

These are operational targets, not absolute guarantees. They should be refined after real corpus benchmarking.

## 7.3 Reliability

- Object storage paths must be deterministic and content-addressed.
- The application should restart cleanly after host reboot.
- Background jobs must be retryable.
- DB backups and ZFS snapshots must be part of the plan, not an afterthought.
- The system must tolerate partial model-server outages by degrading to reduced features.

## 7.4 Privacy and security

- Local-only by default
- No external inference calls unless explicitly enabled
- Encrypt sensitive data at rest where feasible through ZFS native encryption or full-disk encryption
- Preserve audit trails for review actions and exports
- Restrict remote access behind VPN or Tailscale
- Avoid logging raw sensitive content unnecessarily
- Support safe redaction and selective export in later phases

## 7.5 Observability

The system must surface:

- worker queue health
- document pipeline stage per document
- failure reasons
- model processing times
- extraction validation failures
- search latency
- index freshness
- storage consumption by category

## 8. System architecture

## 8.1 High-level services

Recommended v1 services:

- `web`: React + Vite frontend
- `api`: FastAPI backend
- `worker-ingest`: upload normalization and pipeline kickoff
- `worker-docling`: Docling conversion and canonical artifact generation
- `worker-extraction`: Granite and Qwen extraction jobs
- `worker-embeddings`: embedding and reranking jobs
- `postgres`: PostgreSQL with `pg_search` and `pgvector`
- `model-qwen`: local serving of Qwen3-VL inference
- `model-granite`: local serving of Granite extraction inference
- `model-embed`: local serving of embedding models
- optional `reverse-proxy`: Caddy or Traefik
- optional observability stack: Prometheus, Grafana, Loki, NVIDIA exporter

## 8.2 Data flow

1. User uploads document.
2. API writes original bytes to object storage and creates DB records.
3. API creates a durable `pipeline_jobs` row and enqueues the ingest pipeline through the configured transport profile (PGMQ by default).
4. Ingest worker fingerprints file and creates previews.
5. Docling worker creates canonical representation and persists pages, elements, and chunks.
6. Classification job selects document family.
7. Extraction job routes to appropriate extractor and persists raw plus normalized outputs.
8. Validation stage creates review tasks when needed.
9. Embedding worker vectorizes chunks and selected page or visual artifacts.
10. Search indexes become queryable.
11. User files, reviews, searches, and optionally runs analysis.

## 8.3 Service boundaries

The API should remain orchestration-centric and not attempt to run heavy model inference inline. Long-running conversion, extraction, embedding, and reranking work belongs to workers or model-serving endpoints.

## 9. Document understanding stack

## 9.1 Docling as canonical backbone

Docling is the canonical conversion layer because it already provides:

- advanced document conversion across PDFs and other document types
- a unified `DoclingDocument` representation
- layout information
- hierarchy
- table extraction support
- provenance
- structured extraction hooks based on dictionary or Pydantic templates

The application should treat Docling JSON as the durable structural artifact from which many downstream views can be regenerated.

## 9.2 Granite 4.0 3B Vision role

Granite should be used for structured document extraction tasks where table fidelity, chart conversion, and schema-driven KVP extraction matter. It is especially suitable for:

- receipts with awkward line alignment
- invoices with table layouts
- EOB tables
- semantic key-value extraction under explicit JSON Schema control

Granite’s JSON Schema-oriented KVP flow is a strong match for document-family-specific structured extraction.

## 9.3 Qwen3-VL role

Qwen3-VL should be used where broader visual reasoning is needed:

- handwriting
- ambiguous layouts
- mixed media pages
- visually degraded scans
- cross-checking another model’s extraction
- long document structure interpretation
- interactive review assistance in later phases

Use smaller and larger Qwen variants differently:

- a smaller Qwen3-VL variant for faster interactive or cheaper extraction tasks
- a larger Qwen3-VL variant for harder pages, handwriting, or arbitration

## 9.4 Model routing policy

Default routing concept:

- digital-native simple PDF: Docling first, minimal VLM usage
- receipt / invoice / EOB with tables: Docling plus Granite, with Qwen as fallback or validator
- handwriting-heavy note: Docling if useful, then Qwen as primary transcription path
- long legal or reference documents: Docling first, chunk and index for retrieval, use Qwen only where semantic understanding is needed
- mixed-confidence outputs: use validator stage and create review tasks

## 10. Data model expectations

## 10.1 Canonical storage layers

The system stores three categories of truth:

### Original truth
- original uploaded artifact

### Structural truth
- Docling JSON
- page renders
- element rows
- chunk rows
- table artifacts

### Typed truth
- extraction runs
- field and line-item candidates
- canonical accepted fields
- canonical accepted line items
- validated JSON
- normalized fields
- line items
- amounts
- deadlines
- relationships
- review actions

Each layer is versioned and linked.

For v1.3, ordinary UI display, filtering, filing rules, search context, and exports should prefer canonical accepted facts. Candidate facts remain visible in review surfaces and audit/debug views so competing model outputs are not collapsed prematurely.

## 10.2 Provenance model

Every extracted fact should point back to the source using one or more of:

- page number
- bounding box
- element id
- table id and row
- source text
- source engine
- confidence
- extraction run id

For v1.3, page number alone is not sufficient for a trusted extracted value. The evidence object must include page number plus at least one concrete locator such as bounding box, element id, table row reference, text span, or source text excerpt.

## 10.3 Search model

Search should operate over:

- document metadata rows
- chunk text rows
- relationship metadata
- tags and folders as filters
- embeddings for chunks and optionally page visuals

## 11. Output format policy

Different output formats serve different purposes.

### Canonical structural artifact
- Docling JSON

### Human-readable text artifact
- Markdown and plain text derived from the canonical representation

### Typed extraction artifact
- validated JSON using versioned schemas

### ETL / analytics export artifact
- JSONL or CSV from normalized tables

### Table-preserving artifact
- JSON plus HTML or OTSL when available for difficult tables

The application should not force one format to do all jobs.

## 12. Retrieval and ranking design

## 12.1 Lexical retrieval

Use ParadeDB BM25 indexes on at least:

- `documents`
- `document_chunks`
- `parties`

Index relevant metadata needed for search, ranking, and facet queries.

## 12.2 Semantic retrieval

Use pgvector to store embeddings for:

- text chunks
- document-level summaries or title plus metadata text
- selected page-level visual embeddings where appropriate

Default design assumption: standardize the primary text embedding dimension to 1536 or another dimension that fits cleanly within pgvector HNSW constraints. If a model is run at a higher native dimension, either request a smaller output dimension or use model-specific indexing strategies.

## 12.3 Hybrid fusion

Fuse lexical and semantic candidates using RRF or weighted RRF in the application layer or SQL helper layer. RRF is preferred because it combines ranked lists without forcing score normalization across incomparable scoring systems.

## 12.4 Reranking

For top candidate sets, optional reranking may be applied:

- text reranker for text-heavy candidate sets
- multimodal reranker for page-image or visually degraded result sets

Reranking is optional for v1 but the architecture should leave room for it.

## 12.5 Visual retrieval

Visual retrieval is useful for:

- low-text pages
- handwriting-heavy notes
- visually distinctive forms
- layout-sensitive queries

It is not required for every document or page. The system should allow selective visual embedding to control cost and index size.

## 13. User interface requirements

## 13.1 Global UX qualities

The UI must feel calm, fast, and legible. It should not resemble a developer console. Dense technical detail may be available on demand, but the default experience should be clean.
For v1.3 visual direction, use the calm evidence workbench design language in `docs/21_v1.3_Normalization_and_Design_Language.md`.

## 13.2 Required major views

### Inbox
Shows newly ingested items and items needing review.

### Document detail
Shows original document, page thumbnails, extracted fields, evidence, related documents, notes, tags, foldering, and history.

### Search
Supports natural-language query, keyword query, filters, facets, and quick previews.

### Folders
Shows hierarchical folders and smart folders.

### Review queue
Shows tasks by priority, reason, family, and confidence.

### Relationships / timelines
Shows related documents and a timeline-oriented view where useful.

### Analysis workspace
Optional document-set analysis area, separate from normal browsing.

## 13.3 Document detail layout expectations

Recommended layout:

- left: document viewer and thumbnails
- right: structured fields, tables, review status, notes, and related documents
- interaction: clicking a field highlights source evidence
- advanced panel: raw canonical text, raw extraction JSON, model run details, and audit history

## 13.4 Search UX expectations

- search input with query history
- instant filter chips
- sort by relevance, date, amount, review status
- highlighted lexical snippets where relevant
- result cards showing title, family, date, counterparty, amount, folder, and top evidence snippets
- search over smart folders and saved searches

## 14. Security, privacy, and compliance posture

This application is not being positioned as a regulated SaaS platform, but it will store regulated or sensitive material such as medical, legal, and financial documents. Therefore the design should assume sensitive-data handling from day one.

Required behaviors:

- local-only default
- explicit export actions
- audit logging for view / export / delete in later phases
- secure remote access only through trusted network paths
- minimized raw text logging
- no hidden cloud telemetry tied to document content

## 15. Data lifecycle

## 15.1 Ingest lifecycle
new upload -> inbox -> canonical parse -> classification -> extraction -> validation -> review if needed -> filed

## 15.2 Version lifecycle
original stays immutable  
canonical artifacts are append-only by version  
extraction runs are append-only; one run may be marked current  
review can supersede accepted values but should preserve history

## 15.3 Deletion lifecycle
Soft deletion and export/backup awareness are preferred over immediate hard delete for v1. Hard delete flows can be added with extra safety later.

## 16. Acceptance criteria at the product level

The product is ready for an internal v1 milestone when all of the following are true:

- a user can upload scanned and digital-native PDFs;
- originals are preserved immutably;
- documents appear in a browseable inbox immediately;
- Docling conversion artifacts are stored and visible through debug tooling;
- receipt, invoice, and EOB extraction works end-to-end with schema validation;
- evidence highlighting exists for extracted values;
- review tasks exist for bad or uncertain outputs;
- documents can be filed into folders and tagged;
- BM25 search and semantic search both work on real documents;
- hybrid search is clearly better than either alone on a small golden set;
- document relationships can be created and viewed;
- analysis is optional and citation-backed;
- the system survives restart without corruption or orphaned assets.

## 17. Deferred enhancements

Candidates for later phases:

- email ingestion
- mobile companion or share extension
- OCR tuning and deskew pipelines
- active learning loops from corrections
- richer multi-household collaboration UX beyond the single-household baseline
- safe-share redaction workflows
- automatic reminder generation from deadlines and warranty expirations
- rule-based filing suggestions
- LoRA fine-tuning from corrected examples
- richer entity resolution and graph exploration

## 18. Source notes

This specification assumes the following current public capabilities and constraints:

- Docling exposes a unified `DoclingDocument` representation with layout and provenance support, and supports schema-based extraction through dictionary or Pydantic templates.
- Granite 4.0 3B Vision is targeted at enterprise-grade document extraction including tables, charts, and JSON-Schema-driven KVP extraction.
- Qwen3-VL emphasizes strong OCR and long-document structure parsing.
- ParadeDB provides BM25 indexing directly inside Postgres and is designed to work alongside pgvector for hybrid search.
- pgvector HNSW offers better speed/recall tradeoffs than IVFFlat but requires attention to dimensionality and memory.

References:
- Docling overview: https://docling-project.github.io/docling/
- DoclingDocument concept: https://docling-project.github.io/docling/concepts/docling_document/
- Docling information extraction: https://docling-project.github.io/docling/examples/extraction/
- Docling document converter: https://docling-project.github.io/docling/reference/document_converter/
- Granite 4.0 3B Vision model card: https://huggingface.co/ibm-granite/granite-4.0-3b-vision
- Qwen3-VL-8B Instruct model card: https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct
- Qwen3-Embedding-4B model card: https://huggingface.co/Qwen/Qwen3-Embedding-4B
- Qwen3-VL-Embedding repository: https://github.com/QwenLM/Qwen3-VL-Embedding
- vLLM Qwen3-VL recipe: https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3-VL.html
- vLLM structured outputs: https://docs.vllm.ai/en/latest/features/structured_outputs/
- ParadeDB introduction: https://www.paradedb.com/blog/introducing-paradedb
- ParadeDB create index: https://docs.paradedb.com/documentation/indexing/create-index
- ParadeDB simple introduction: https://docs.paradedb.com/welcome/introduction
- ParadeDB indexing JSON: https://docs.paradedb.com/documentation/indexing/indexing-json
- ParadeDB BM25 scoring: https://docs.paradedb.com/documentation/sorting/score
- ParadeDB facets: https://docs.paradedb.com/documentation/aggregates/facets
- ParadeDB RRF explainer: https://www.paradedb.com/learn/search-concepts/reciprocal-rank-fusion
- ParadeDB self-hosted extension: https://docs.paradedb.com/deploy/self-hosted/extension
- pgvector repository: https://github.com/pgvector/pgvector
