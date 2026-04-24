# Model routing and output contracts

## 1. Purpose

This document defines how the system should use Docling, Granite, and Qwen together, and what output shapes the application expects from each stage.

## 2. Canonical output policy

The system persists multiple output forms because each serves a different job.

### 2.1 Canonical structural artifact
- `docling.json`
- optional `docling.md`
- optional `docling.html`

Purpose:
- stable representation
- debugging
- later re-chunking
- later re-extraction

### 2.2 Raw model output artifacts
- raw Granite result JSON
- raw Qwen result JSON or text
- model trace metadata

Purpose:
- reproducibility
- debugging
- later normalization improvements

### 2.3 Normalized extraction artifact
- strict, schema-validated JSON

Purpose:
- UI rendering
- relational persistence
- analytics
- export

## 3. Routing defaults

### 3.1 Digital-native PDF, simple layout
Preferred path:
- Docling conversion
- schema extraction from canonical text or structured data
- use VLM only if needed

### 3.2 Receipt / invoice / EOB with layout complexity
Preferred path:
- Docling parse
- Granite table/KVP extraction
- Qwen fallback or validator when alignment is unclear

### 3.3 Handwritten note
Preferred path:
- preview generation
- Qwen as primary transcription route
- review-required by default unless quality is unexpectedly high

### 3.4 Long legal or reference PDF
Preferred path:
- Docling parse
- chunk and index
- optional extraction for dates, parties, or obligations
- optional Qwen analysis later

## 4. Output requirements for all extraction models

Every extraction run must persist:

- document id
- schema name and version
- source engine
- model name and version
- prompt version
- raw output artifact reference
- normalized JSON
- validation JSON
- confidence summary
- created timestamp

## 5. Evidence contract

At minimum, an evidence object must allow the UI to locate the source. For any extracted value that is shown as trusted, page-only provenance is not enough.

Recommended evidence fields:
- `page_number`
- `bbox`
- `element_id`
- `table_id`
- `row_index`
- `text_span`
- `source_text`
- `source_engine`
- `confidence`

Not every field will populate every locator, but trusted fields must carry page number plus at least one stronger locator: `bbox`, `element_id`, `table_id` plus row, `text_span`, or `source_text`. Page-only evidence may be stored for debugging, but it is insufficient for automatic canonical promotion.

## 6. Validation contract

Normalization is not complete until:
- JSON Schema validation passes;
- required fields are checked;
- arithmetic checks are run where relevant;
- cross-field consistency checks are run.

Examples:
- receipt subtotal should match line items when possible
- invoice due date should not precede issue date
- EOB service-line totals should be internally plausible

## 7. Structured output strategy

Preferred strategy:
- use explicit JSON Schema or Pydantic-derived schema for extraction;
- use constrained / structured decoding where the serving stack supports it;
- still run post-hoc validation because structure compliance is not semantic correctness.

## 8. Schema evolution rule

When a schema changes:
- create a new schema version;
- do not reinterpret old accepted data silently;
- allow re-extraction into the new version;
- preserve old extraction runs.

## 9. Why Docling is treated as canonical

Docling’s current documentation emphasizes a unified `DoclingDocument` type with text, tables, pictures, document hierarchy, layout information, and provenance support, as well as schema-driven extraction hooks. That makes it the right stable middle layer for this application.

## 10. Why Granite is used selectively

Granite 4.0 3B Vision’s current model card emphasizes enterprise-grade document extraction, including table extraction, chart extraction, and JSON-Schema-oriented key-value extraction. That makes it especially strong for layout-sensitive business documents.

## 11. Why Qwen3-VL is used selectively

Qwen3-VL’s current public model materials emphasize OCR, long-document structure parsing, and stronger general multimodal reasoning. It is therefore a strong fallback and arbitration model, and a good route for handwriting and visually degraded pages.

## 12. Why text and visual embeddings are separated conceptually

Text embeddings should be the default because they are smaller, simpler, and cover most searches. Visual embeddings should be added selectively for low-text or layout-sensitive pages. They are a retrieval enhancement, not the foundation of the whole application.

## 13. References

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
