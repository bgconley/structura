# ADR 0003: Phase 3 Docling Canonical Parse

Date: 2026-04-26

## Status

Accepted

## Context

Phase 3 introduces the canonical parse layer that later classification, extraction, review,
search, and evidence workflows build on. The phase must persist Docling artifacts, page text,
elements, tables, chunks, page preview assets, job history, and a protected debug surface without
implementing Phase 4 extraction or review behavior.

Official Docling documentation confirms the Python package install path and the
`DocumentConverter.convert(...)` workflow, with exports available from the converted document.
PyPI reported `2.91.0` as the current release during implementation, so the runtime dependency is
bounded as `docling>=2.91,<3`.

## Decisions

- The API upload route remains thin. It stores the immutable original and enqueues `ingest`,
  `preview`, and `docling_convert` jobs with IDs/object metadata only.
- The Docling worker is a real queue consumer at `workers.docling.worker`; Compose no longer runs
  the placeholder for `worker-docling`.
- Vendor-specific Docling imports are isolated in `workers/docling/converter.py` and happen lazily
  at conversion time so tests and non-worker imports do not require Docling to be installed.
- Parse data contracts live in `lib/documents/parse_models.py`, asset/orchestration behavior lives
  in `lib/documents/canonical_parse.py`, and relational row replacement lives in
  `lib/documents/parse_repository.py`.
- Derived parse artifacts use versioned current-asset semantics. Reprocessing marks previous
  current assets non-current, inserts changed versions, and replaces relational page/element/table/
  chunk rows atomically.
- `documents.canonical_asset_id` points at the current `docling_json` asset after successful
  conversion. The original asset remains available through the `original` asset role.
- Page previews remain deterministic SVG derivatives for Phase 3. They are linked through
  `document_pages.image_asset_id` and `document_pages.thumbnail_asset_id`, refreshed after parse,
  and can be replaced by higher-fidelity renderers later without changing the asset/page seam.
- Parse debug data is exposed through a protected admin-scoped route,
  `/api/v1/documents/{documentId}/parse-debug`, with bounded result limits and API asset URLs only.

## Consequences

- Phase 4 can attach extraction candidates and trusted values to persisted page numbers, element
  references, table summaries, chunks, and current Docling artifact metadata.
- The canonical parse layer can be re-run safely without accumulating duplicate current assets or
  stale parse rows.
- The primary viewer workflow remains unchanged while admin diagnostics can inspect canonical parse
  state on demand.

## Deferred Work

- Phase 3 does not implement classification, extraction candidates, canonical field promotion,
  model-based review workflows, search ranking, or smart-folder execution.
- The SVG preview renderer is an explicit Phase 3 fallback. Higher-fidelity PDF/image rasterization
  can replace it behind the same `page_image` and `thumbnail` asset roles.
