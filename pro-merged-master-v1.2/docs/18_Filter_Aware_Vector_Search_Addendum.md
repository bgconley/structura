# 18 — Filter-Aware Vector Search Addendum

Historical note: In v1.3 this document is background rationale unless explicitly referenced by the ADR summary or the current normalization doc.

Prepared: 2026-04-23

## 1. Purpose

This addendum makes an important search caveat explicit: vector retrieval with approximate HNSW indexes and SQL filters requires careful planning. It is not enough to create a vector index and append `WHERE` clauses.

## 2. Problem

A user query will often include structured filters:
- folder;
- household/ACL;
- document family;
- date range;
- amount range;
- counterparty/contact;
- review status;
- sensitivity.

Approximate vector search may retrieve nearest vectors first and apply filters afterward. That can under-return when many top semantic candidates fail filters.

## 3. Required mitigations

Use several techniques together:

1. Keep strong B-tree indexes on common filters.
2. Keep BM25 candidate retrieval as a parallel path.
3. Use chunk-level retrieval, not only whole-document vectors.
4. Denormalize common filter context onto chunks and embedding metadata.
5. Use partial vector indexes for high-volume modalities or document families when justified.
6. Tune `hnsw.ef_search` per query class.
7. Use iterative scans if available in the selected pgvector version.
8. Fuse lexical and vector candidates before reranking.
9. Always apply ACL filters authoritatively before returning results.

## 4. Chunk projection requirements

Each retrieval chunk should carry:
- `document_id`;
- `household_id`;
- document family;
- document subtype;
- document date;
- primary folder;
- sensitivity;
- counterparty/contact snapshot;
- page range;
- text;
- metadata JSON.

This avoids expensive joins for every candidate and gives search more filter context.

## 5. Hybrid search flow

Recommended flow:

```text
query
  -> parse filters
  -> lexical BM25 retrieval
  -> vector retrieval with filter-aware planning
  -> optional visual retrieval
  -> RRF fusion
  -> optional rerank
  -> final SQL ACL check
  -> grouped document results
```

## 6. Result explanation

Every search result should explain:
- matched text or field;
- page range;
- ranking sources used;
- applied filters;
- whether semantic, lexical, field, or relationship evidence contributed.

## 7. Evaluation requirements

Search evaluation should include:
- exact identifier queries;
- natural-language conceptual queries;
- filtered semantic queries;
- date/amount/entity/folder filters;
- ACL visibility tests;
- negative tests where a document should not appear.

## 8. Implementation consequences

Add:
- denormalized chunk columns;
- search query planner module;
- BM25-only, vector-only, hybrid test paths;
- trace/debug mode for candidate lists;
- search quality benchmark fixtures.
