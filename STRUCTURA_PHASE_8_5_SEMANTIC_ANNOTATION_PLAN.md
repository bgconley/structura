# Structura Phase 8.5 Semantic Annotation Plan

## Purpose

Phase 8.5 adds the semantic intelligence layer between Docling physical parsing and
Granite structured extraction.

The canonical pipeline is:

```text
Document / image
-> Docling physical parse
-> Qwen3-VL-4B smart semantic annotation manifest
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

## User-Selectable Model Modes

Default Smart Parse uses Qwen3-VL-4B through the same Docling-grounded semantic
harness and manifest contract originally built for the 2B path. Qwen3-VL 8B
must never be invoked by default ingest, validation review policy, low
confidence alone, or private corpus standard validation.

Qwen3-VL 8B has exactly two authorization paths:

1. **High Quality Parse**: the user explicitly selects a Qwen3-VL 8B pass for
   the document.
2. **Allow 8B Rescue**: the user explicitly permits one bounded Qwen3-VL 8B
   rescue if the rescue policy classifies the issue as semantically recoverable.

If neither option is selected, uncertain, incomplete, unreconciled, or ambiguous
outputs become `needs_human_review` or `insufficient_signal`; they do not
escalate to Qwen3-VL 8B.

Persisted semantic job intent fields:

- `semantic_quality_mode`: `smart` or `high_quality`
- `allow_8b_rescue`: `true` or `false`
- `requested_by_user_id`
- `user_intent_reason`

## Runtime Profiles

- Smart Parse: `qwen3-vl-4b-semantic:v1`
- High Quality: `qwen3-vl-8b-semantic-hq:v1`, user-selected only
- Rescue: `qwen3-vl-8b-semantic-hq:v1`, one user-permitted rescue only
- Structured extraction: `granite-4.0-3b-vision-bf16:v1`

The Qwen3-VL-4B smart profile first attempts four page images per semantic
request, preserving the historical Qwen3-VL-2B fan-in shape for short PDFs.
Each Smart Parse page image is bounded to planner resolution through Qwen's 32x
visual-token guidance: 256 minimum and 2560 maximum visual tokens per image
(`shortest_edge = 262144`, `longest_edge = 2621440`). Exact Docling page
coverage remains mandatory; if a multi-image request omits a Docling page or
exceeds the model context, the gateway may retry that window as one-page
requests while keeping whole-document Docling context in the prompt. This
planner-resolution budget does not downscale Docling originals globally and
does not weaken Granite page/crop/table inputs.

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
7. `RescuePolicy` may enqueue one bounded `rescue` semantic pass only when the
   user persisted `allow_8b_rescue = true`, the issue is semantically
   recoverable, and the same document/region/failure class has not already been
   rescued.

Do not treat `validation.needs_review`, low confidence, high-risk document
family, or human-review policy as rescue triggers by themselves.

## Outcome Vocabulary

- `extracted_cleanly`: candidates are extracted and validation/evidence policy passes.
- `needs_human_review`: candidates exist but confidence, reconciliation,
  evidence, or policy requires review.
- `insufficient_signal`: the source is too degraded, ambiguous, blank, or
  unreadable to produce reliable candidates.
- `no_extraction_target`: the page/region is boilerplate, blank, irrelevant, or
  non-extractable.
- `pipeline_failed`: runtime/system failure only, such as timeout, invalid model
  response, worker crash, storage error, DB error, or contract violation.

Document-quality ambiguity must create review/diagnostic state, not failed jobs.
Runtime defects are the only `pipeline_failed` cases.

## API/UI Surface

- `GET /api/v1/documents/{documentId}/semantic-annotations/current`
- `POST /api/v1/documents/{documentId}/semantic-annotations/high-quality`
- `POST /api/v1/documents/{documentId}/semantic-annotations/allow-8b-rescue`

The Viewer exposes Smart Parse manifest diagnostics, a deliberate High Quality
Parse action, and a separate Allow 8B Rescue action. There is no hidden
automatic escalation.

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
- Standard ingest never enqueues Qwen3-VL 8B.
- `needs_review` alone never enqueues rescue.
- Rescue requires persisted `allow_8b_rescue = true` and is capped/deduped.
- Private corpus standard mode does not secretly run High Quality.
- Quality outcomes stay distinct from runtime `pipeline_failed`.
- OpenAPI and event contracts cover semantic annotation routes/jobs.
- GPU validation must include unit, integration, SAST/type checks, web build, Compose
  config, and live browser smoke against the GPU-hosted app.
