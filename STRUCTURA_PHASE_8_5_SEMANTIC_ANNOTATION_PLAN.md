# Structura Phase 8.5 Semantic Annotation Plan

## Purpose

Phase 8.5 adds the semantic intelligence layer between Docling physical parsing and
Granite structured extraction.

The canonical pipeline is:

```text
Document / image
-> Docling physical parse
-> Qwen3-VL semantic annotation manifest
-> Granite 4.0 3B Vision targeted extraction
-> validators / provenance / review
-> canonical facts + search/evidence layer
```

Docling remains the source of physical truth: pages, text, element IDs, table IDs,
coordinates, page images, and provenance. Qwen is a semantic planner. Granite is the
structured extractor. Validators and human review remain the truth gate for canonical
facts.

## Non-Negotiable Rules

1. Qwen annotations are never canonical facts.
2. Qwen must prefer Docling `page_id`, `element_id`, and `table_id` grounding.
3. Ungrounded Qwen regions are stored as `unmatched_region`, low trust, and
   review-required.
4. Granite extraction jobs must carry semantic annotation/region IDs when they are
   targeted by the semantic manifest.
5. Model provenance must reflect the actual adapter invoked.
6. Phase 9 analysis may use semantic annotations for planning, but answers must cite
   original document/page/region evidence.

## Runtime Profiles

- Smart Parse: `qwen3-vl-2b-semantic:v1`
- High Quality / Rescue: `qwen3-vl-8b-semantic-hq:v1`
- Structured extraction: `granite-4.0-3b-vision-bf16:v1`

Fixture mode remains deterministic and must not claim Qwen or Granite provenance.

## Data Model

Migration `075_phase8_5_semantic_annotations.sql` adds:

- `document_semantic_annotations`
- `page_semantic_annotations`
- `semantic_region_annotations`

Only one current annotation may exist per document/profile/quality mode. New manifests
supersede prior current manifests atomically.

## Job Flow

1. `worker-docling` completes Docling conversion.
2. Docling completion enqueues `semantic_annotate` on `semantic-annotations`.
3. `worker-semantic-annotations` loads Docling context and page images.
4. The semantic gateway produces and validates a Qwen manifest.
5. The manifest is persisted and grounded Granite extraction jobs are queued.
6. `worker-extraction` resolves `semantic_region_id` and passes the task to Granite.
7. Validation failure can enqueue a bounded `rescue` semantic pass.

## API/UI Surface

- `GET /api/v1/documents/{documentId}/semantic-annotations/current`
- `POST /api/v1/documents/{documentId}/semantic-annotations/high-quality`

The Viewer exposes Smart Parse manifest diagnostics and a High Quality Pass button.

## Phase 9 Seams

Phase 9 analysis should consume semantic manifests as planning metadata only. It must
ground all generated notes, answers, and timelines back to document evidence rather than
using semantic annotations as standalone truth.

## Validation Gates

Minimum Phase 8.5 gates:

- Migration-from-scratch includes `075_phase8_5_semantic_annotations.sql`.
- Semantic manifest policy rejects unknown semantic types, unsupported Granite tasks,
  invalid Docling IDs, and unreviewed unmatched regions.
- Qwen smart/HQ gateways read page images and preserve truthful provenance.
- Granite targeted extraction receives semantic region context.
- OpenAPI and event contracts cover semantic annotation routes/jobs.
- GPU validation must include unit, integration, SAST/type checks, web build, Compose
  config, and live browser smoke against the GPU-hosted app.
