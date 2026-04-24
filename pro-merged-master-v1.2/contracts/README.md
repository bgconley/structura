# Contracts directory

This directory contains machine-readable interfaces for the application.

## Contents

- `api/openapi.yaml`  
  The HTTP API contract for the first implementation slice, including upload and auth/session surfaces.
- `schemas/*.json`  
  JSON Schemas for normalized extraction outputs, analysis notes, and review actions.
- `events/*.json`  
  Queue/job payload schemas used by the async pipeline.

## Contract design rules

1. Schema names and versions are explicit and immutable.
2. Extraction contracts are intentionally stricter than raw model outputs.
3. Every trusted field that originates from a document must allow evidence linkage with page number plus a concrete locator.
4. Event payloads are idempotent and correlation-friendly.
5. API payloads may be a strict subset of the richer internal extraction contracts.
6. Auth expectations must be explicit: session-cookie and API-token security behavior should never be left implicit in prose alone.

## Versioning policy

- New required fields or semantic changes create a new schema version.
- Backward-compatible optional additions may remain in the same minor document version, but production releases should still stamp the effective schema version into each stored extraction.
- Do not silently reinterpret accepted historical extractions. Re-extract into a new version instead.

## Source notes

The design of these contracts follows the system requirements documented elsewhere in this pack and was informed by the current public documentation for Docling, Granite 4.0 Vision, Qwen3-VL, vLLM structured outputs, ParadeDB, and pgvector.

## References

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


## v1.1 added contracts

The golden-master merge adds these contracts:

- `schemas/field_candidate.v1.schema.json`
- `schemas/canonical_field.v1.schema.json`
- `schemas/filing_rule.v1.schema.json`
- `schemas/folder_acl.v1.schema.json`

These support candidate-vs-canonical extraction, review/adjudication, transparent filing automation, and household/folder ACL.

Alignment note:

- Upload and ingest `source` identifiers in the API and event contracts should match `database/010_types_and_enums.sql`.
- Auth/session payloads in `api/openapi.yaml` are intended to be satisfiable directly from baseline schema state, not hidden framework-only session objects.
