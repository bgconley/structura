# Testing, QA, and release strategy

## 1. Quality philosophy

Document AI systems fail quietly when they are not tested against fixed examples, field-level expectations, and retrieval benchmarks. This project requires both traditional software tests and corpus-based quality evaluation.

## 2. Test categories

### 2.1 Unit tests
Use for:
- schema validation
- helper functions
- evidence builders
- amount arithmetic checks
- query filter parsing
- storage path generation
- duplicate detection helpers

### 2.2 Integration tests
Use for:
- upload to object store plus DB row creation
- canonical parse worker persistence
- extraction run persistence
- embedding generation persistence
- search endpoint behavior
- review correction flow

### 2.3 End-to-end tests
Use for:
- upload document -> inbox -> parse -> extraction -> review -> filed
- search and open result
- correction with evidence jump
- export bundle creation

### 2.4 Corpus evaluation tests
Use for:
- classification accuracy
- extraction field correctness
- search benchmark results
- regression comparison across prompt or model changes

## 3. Golden corpus design

Maintain a curated corpus under secured local storage, not in public source control unless sanitized. Each sample should have:

- original file
- document family label
- expected key fields
- expected review expectation
- search queries that should retrieve it
- notes about ambiguity or known difficulty

Suggested starter corpus composition:

- 10 receipts
- 10 invoices
- 10 EOBs / medical bills
- 5 warranties
- 5 legal notices or agreements
- 5 handwritten notes
- 5 long reference PDFs

## 4. Extraction evaluation

For each schema, measure at least:

- required field presence rate
- exact-match accuracy for easy header fields
- numeric correctness for totals
- arithmetic consistency pass rate
- review-task creation rate on bad inputs

Do not rely only on overall JSON equality. Field-level outcomes matter more.

## 5. Search evaluation

Maintain a benchmark file with natural-language and lexical queries. For each query, define expected top-k matches or at least expected inclusion sets.

Example benchmark cases:

- “whole foods bananas receipt”
- “MRI EOB where insurance paid part”
- “dishwasher warranty”
- “contract amendment”
- “return window open”

Measure:
- hit rate at k
- mean reciprocal rank where practical
- qualitative snippet usefulness

## 6. Manual QA checklist for each release

- upload a clean digital PDF
- upload a messy scanned receipt
- upload a handwriting-heavy note
- verify viewer rendering
- verify canonical parse debug view
- verify field evidence jump
- verify search with lexical query
- verify search with semantic query
- verify folder and tag operations
- verify a review correction
- verify export bundle

## 7. Regression discipline

When changing:
- prompts
- schema versions
- model versions
- chunking strategy
- BM25 index definition
- embedding model or dimension
- hybrid ranking weights

run the golden corpus and store before / after results. Regressions must be deliberate and documented.

## 8. Release train suggestion

### Alpha
- ingest, browse, manual filing, canonical parse

### Beta
- structured extraction for key schemas, review queue, lexical search

### RC
- hybrid search, relationships, backups tested, admin visibility

### GA-like internal release
- analysis optional, cited, bounded; benchmark results acceptable

## 9. Production-like acceptance gates

Require:
- zero critical data-loss bugs
- zero silent overwrite of originals
- no broken provenance links on tested samples
- migrations pass from scratch
- restore rehearsal passes
- benchmark quality above team-approved threshold

## 10. Tooling recommendations

- unit and integration tests in normal CI
- local corpus evaluation script outside public CI if data is sensitive
- test fixtures for JSON schemas
- notebook or report generation for retrieval quality comparisons
