# Structura Phase 8.5 Semantic Annotation Plan

Current authority: [ADR 0008](docs/adr/0008-qwen38-27b-ingestion.md) selects **Qwen3.8-27B BF16 on Oxcart** for ingestion. [ADR 0009](docs/adr/0009-qwen-native-document-parsing.md) makes Qwen-native full-document parsing the target, superseding mandatory Docling and selection-only extraction while preserving original evidence, truthful provenance, validation and review. The [production completion plan](STRUCTURA_PRODUCTION_COMPLETION_PLAN.md) and X-01–X-08 track implementation, migration and release validation. These are accepted architecture decisions; application/runtime integration remains open.

## Purpose

Phase 8.5 combines complete Qwen-native structural parsing, grounded semantic planning and bounded extraction. Semantic manifests remain planning metadata; they do not replace full searchable text/tables or typed extraction contracts.

The selected target pipeline, pending implementation, is:

```text
Document / image
-> lightweight page inventory, original-page rendering and available native text
-> Oxcart Qwen3.8-27B BF16 full searchable structural parse
-> explicit semantic planning and bounded extraction task outputs
-> validators / provenance / review
-> canonical facts + search/evidence layer
```

Immutable originals remain the source. The thin source layer owns actual page inventory, images and coordinate transforms; the versioned Qwen parse supplies derived text, elements, tables, reading order and locators. Native text and model transcription keep distinct provenance throughout indexing, candidates and claims. Matching a value to its own generated transcript is not independent verification. Validators and human review remain the acceptance gate for facts. Docling supports temporary migration/comparison and genuine historical artifacts; neither its presence nor agreement is required for the new pipeline.

## Non-Negotiable Rules

1. Qwen annotations are never canonical facts.
2. Qwen must ground to actual document/page ownership and versioned parse `element_id`/`table_id` references where applicable. Validate coordinates and transforms against original pages; generated locators alone do not prove content accuracy.
3. Ungrounded Qwen regions are stored as `unmatched_region`, low trust, and
   review-required.
4. Extraction candidates must carry source/run and semantic annotation/region IDs where applicable; a simplified call must preserve equivalent evidence lineage.
5. Model provenance must reflect the actual adapter invoked.
6. Phase 9 analysis may use semantic annotations for planning, but answers must cite
   original document/page/region evidence.

## Model Modes

Default Smart Parse is planned to use the existing Oxcart Qwen3.8-27B BF16 engine. Explicit task profiles distinguish full structural parsing, semantic planning and extraction, even when one bounded request returns several typed outputs. Version the existing manifest contract where its Docling assumptions change under ADR 0009. Planning annotations remain separate from extraction candidates and accepted facts; preserve compatibility for genuine old records.

The previous Qwen3-VL-8B FP8 and 4B profiles retain historical/canary lineage. Neither is required to run for 27B selection or release acceptance.

The older separate `model-qwen` High Quality / rescue service remains disabled
and deferred. Do not introduce hidden second-pass escalation from validation,
low confidence, or review policy. If a future HQ/rescue mode is re-enabled, it
must be explicitly specified in a new plan and kept separate from the default
Smart Parse pass.

Uncertain, incomplete, unreconciled, or ambiguous outputs become
`needs_human_review` or `insufficient_signal`; they do not trigger another
automatic Qwen pass.

Active semantic job intent fields:

- `semantic_quality_mode`: `smart`
- `requested_by_user_id`
- `user_intent_reason`

Legacy `high_quality` and `allow_8b_rescue` values must not be emitted by
standard ingest. Any future re-enable requires a new plan and a separate
release gate.

## Runtime Profiles

- Selected engine: existing `qwen38-27b-bf16-oxcart` on Oxcart port `18012`, authenticated through configured adapters.
- Proposed logical engine profile: `qwen3.8-27b-bf16-ingestion:v1`, to be implemented with versioned task/prompt/schema profiles.
- Historical comparators: `qwen3-vl-8b-fp8-semantic:v1`, `qwen3-vl-4b-semantic:v1`.
- Target parser/extractor: bounded Qwen-native parsing and extraction through the resident service, with exact native-source copying when useful and explicit model-backed review policy.
- Explicit comparison/rollback only: `granite-4.0-3b-vision-bf16:v1`

No active runtime profile exists for a separate second-pass Qwen escalation
service.

The old `model-qwen-semantic:8104` service used a 32K context, FP8 KV and four planner-resolution page images. Those are historical 8B settings, not configuration to copy onto the resident 27B service. Inspect the existing endpoint and validate 27B request budgets, schema support, final-answer parsing, image fidelity and shared-client latency without restarting it. Exact source page inventory and original image fidelity remain mandatory. Blackbird's proposed text/visual embedding services encode ingestion/reindex documents and pages plus search queries under ADR 0007.

Fixture mode remains deterministic and must not claim Qwen or Granite provenance.

## Qwen Smart Planner Contract

The pre-migration Smart Parse prompt version is `phase8_5-semantic-smart-v3`. X-01 must record its 27B compatibility and version prompt/schema changes. The semantic task remains recall-oriented planning; full structural parsing and extraction use separate explicit contracts under ADR 0009. The following requirements apply to the semantic output only, not to the full-text parse:

- Qwen must account for every input page image before selecting extraction targets.
- Qwen must emit all materially extractable regions that could change downstream
  factual coverage, bounded to 12 regions per request and usually no more than
  three materially extractable regions per page.
- Qwen must not output field values, money amounts, dates, names, addresses, or
  canonical facts.
- Qwen must keep extraction routing grounded to versioned source/parse IDs and use
  `unmatched_region` only when a useful target cannot be grounded.
- Qwen should emit competing `document_type_candidates` with evidence terms when
  family fit is ambiguous, rather than forcing escrow/title/dispute/generic
  documents into invoice, receipt, or medical EOB.
- Qwen page annotations may carry `page_family_hints`, `continuation_group`,
  a provider-neutral table signal, `requires_cross_page_context`, and
  `material_region_count_hint`.
- Qwen region annotations may carry `importance`, `source_signal`,
  `coverage_role`, `extraction_scope`, `requires_full_page_image`,
  `continuation_group`, `must_extract_reason`, `negative_routing_reason`,
  `min_expected_items`, and advisory `visual_bbox_hint`.
- `planner_notes` are for routing warnings such as weak table text,
  conflicting family anchors, or continuation groups that require full-page
  image context.

Source/parse context sent to Qwen includes whole-document outline, first/last page
snippets, lexical anchors, family hint tension, table inventory, and focused
page details. It intentionally omits token-heavy bboxes, page image hashes, and
the legacy duplicate `pages` alias in model prompts.

The legacy `docling_table_signal` field may remain in historical manifests. Version its neutral replacement without falsely attributing Qwen-derived signals to Docling. Full-parse tasks separately require all ordinary document text, page coverage, table/cell relationships, continuation handling and original-coordinate locators; semantic region caps must never truncate searchable parsing.

The semantic canary can enforce private expectations through
`scripts/gpu/run_phase8_5_semantic_canary.py --expectations-json <file>`. The
committed example at
`tests/fixtures/semantic_annotations/semantic_canary_expectations.example.json`
documents the private canary shape without committing private PDFs.

## Data Model

Migration `075_phase8_5_semantic_annotations.sql` adds:

- `document_semantic_annotations`
- `page_semantic_annotations`
- `semantic_region_annotations`

Only one current annotation may exist per document/profile/quality mode. New manifests
supersede prior current manifests atomically.

New manifests also bind to their source/parse version and run generation. Supersession must preserve prior evidence IDs and historical annotation views; it must not attach old regions to a newly segmented parse by ID coincidence.

## Job Flow and planned migration

The current Docling-first region-job implementation is migration input. X-03/X-05 replace it with bounded Qwen-native parsing and fenced per-document orchestration under ADR 0009. Fewer calls do not relax run-generation, evidence or cancellation requirements.

1. Thin source handling inventories real pages and stages original images plus available native text.
2. The Qwen parse adapter produces a versioned complete structural artifact in bounded page batches with continuation/checkpoint state.
3. Semantic planning loads the corresponding source/parse version and page images; a combined response must still have separately typed parse, planning and candidate outputs.
4. The semantic gateway produces and validates a Qwen manifest linked to that version.
5. The manifest is persisted and grounded extraction work is scheduled with run/claim ownership.
6. `worker-extraction` performs bounded 27B extraction or useful native-source copying under the appropriate contract; claims and review policy control resulting candidates. Atomic current-version publication and generation-aware indexing preserve historical evidence and corrections.
7. Uncertain, unsupported, or incomplete output is classified as
   `needs_human_review`, `insufficient_signal`, `no_extraction_target`, or a
   planner skip. It does not enqueue a second Qwen pass.

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

The Viewer exposes Smart Parse manifest diagnostics only. There are no active
second-pass Qwen controls in the default runtime, and there is no hidden
automatic escalation.

## Phase 9 Seams

Phase 9 analysis should consume semantic manifests as planning metadata only. It must
ground all generated notes, answers, and timelines back to document evidence rather than
using semantic annotations as standalone truth.

## Validation Gates

Minimum Phase 8.5 gates:

- Migration-from-scratch includes `075_phase8_5_semantic_annotations.sql`.
- Semantic manifest policy rejects unknown semantic types, unsupported extraction tasks,
  invalid source/parse ownership or versioned IDs, and unreviewed unmatched regions.
- Authenticated 27B Smart Parse/selection/vision calls preserve exact model/task lineage, source context and evidence; no 27B output is labeled 8B or Granite.
- Structured-output schemas and bounded response handling work for the new profile, rather than relying on an 8B-specific equality branch.
- Standard ingest runs one Smart Parse semantic pass and never enqueues hidden
  second-pass Qwen escalation.
- `needs_review`, low confidence, high-risk family, or human-review policy never
  enqueues another Qwen pass.
- Private corpus standard mode does not secretly run a second semantic pass.
- Quality outcomes stay distinct from runtime `pipeline_failed`.
- OpenAPI and event contracts cover semantic annotation routes/jobs.
- GPU validation must include unit, integration, SAST/type checks, web build, Compose
  config, and live browser smoke against the GPU-hosted app.
- The selected 27B path passes annotated full-text/structure/field/row/classification/evidence gates with Docling disabled. Complete ingestion, indexing, search, Viewer navigation and parser recovery work without Docling; old artifacts remain readable. Same-transcript matches cannot establish independent source accuracy.
- Existing-client contention on Oxcart, ingestion/reindex embeddings and query/search latency on the chosen Blackbird profile are measured. Generation-aware cutover/rollback preserves historical evidence and later human corrections.
