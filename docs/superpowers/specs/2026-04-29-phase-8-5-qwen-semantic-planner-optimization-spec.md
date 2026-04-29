# Phase 8.5 Qwen3-VL-4B Semantic Planner Optimization Spec

## Purpose

This spec defines the next Phase 8.5 hardening pass: isolate Qwen3-VL-4B as a
semantic planner, raise planner recall without turning Qwen into a fact
extractor, and make planner output rich enough that Granite receives the right
regions, in the right order, with the right grounding.

The canonical pipeline remains:

```text
Docling physical parse
-> Qwen3-VL-4B semantic planner
-> Granite 4.0 3B Vision targeted structured extraction
-> validators / provenance / human review policy
-> canonical facts + evidence/search layer
```

Docling remains the physical truth layer. Qwen remains a planner. Granite
remains the extractor. Validators and review policy remain the promotion gate.

## Problem Statement

The current Smart Parse planner contract is suppressing useful routing signal.
The local code and recent corpus behavior show three concrete pressure points:

1. The Qwen prompt asks for sparse output: "select only the highest-value
   Granite routing targets" and "do not enumerate every visible field."
2. The model-output schema caps regions at six total per request, which is too
   tight for multi-page invoices, service records, orders, and mixed-summary
   documents.
3. `SemanticAnnotationService` caps Smart Parse Granite fanout at four jobs,
   which means even improved planner recall can be silently discarded.

This is not just a model-quality problem. It is an adapter and contract
problem. BMW demonstrated the failure mode clearly: the document had materially
useful service-line and payment regions, but the planner contract encouraged the
model to under-report them.

## Scope

This pass is intentionally Qwen-first.

In scope:

- Qwen semantic prompt contract
- semantic model-output and manifest schema additions
- Docling context shape for semantic planning
- Qwen output normalization, validation, merge, and scoring
- Smart Parse fanout budgeting between planner output and Granite enqueue
- semantic-only canary harness and private canary assertions
- Phase 8.5 planning/docs updates needed to codify the new planner behavior

Out of scope for this pass:

- new canonical fact schemas
- making Qwen output canonical invoice/receipt/EOB JSON
- replacing Granite as the structured extractor
- Phase 9 analysis work
- re-enabling automatic or default Qwen3-VL-8B behavior
- fine-tuning Qwen or Granite

## Source-Backed Guidance

The implementation should follow these source-backed rules:

1. Qwen is strong at document parsing, layout, OCR, and positional output; its
   own cookbook emphasizes layout-aware structured outputs such as QwenVL HTML,
   Markdown, tables, and coordinate-bearing content rather than only minimal
   classification JSON.
2. Structured output still needs prompt discipline. Alibaba's Qwen structured
   output guidance says prompts should explicitly describe schema fields, field
   rules, and examples, and outputs should be validated before downstream use.
3. vLLM structured output is useful but not sufficient. Use backend-guided
   schema output where supported, but keep prompt-level schema instructions and
   local validation because backend/model behavior can drift.
4. Parse quality remains upstream truth. If Docling context hides or distorts
   layout clues, planner quality will degrade regardless of prompt tuning.
5. Production extraction systems do better when prompts behave like versioned
   API contracts, preserve uncertainty explicitly, and prefer grounded partial
   output over sparse "best guess" output.

Primary sources used for this spec:

- Qwen3-VL-4B model card:
  `https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct`
- Qwen document parsing cookbook:
  `https://github.com/QwenLM/Qwen3-VL/blob/main/cookbooks/document_parsing.ipynb`
- Qwen OCR cookbook:
  `https://github.com/QwenLM/Qwen2.5-VL/blob/main/cookbooks/ocr.ipynb`
- Qwen document parsing docs:
  `https://www.mintlify.com/QwenLM/Qwen3-VL/capabilities/document-parsing`
- Alibaba structured output guidance:
  `https://www.alibabacloud.com/help/en/model-studio/qwen-structured-output`
- vLLM structured outputs:
  `https://docs.vllm.ai/en/latest/features/structured_outputs/`
- Docling document model:
  `https://docling-project.github.io/docling/concepts/docling_document/`
- Docling extraction examples:
  `https://docling-project.github.io/docling/examples/extraction/`

Directional practitioner/research inputs used to shape safeguards:

- Reducto extraction best practices
- Databricks reliable PDF extraction writeup
- AWS multi-page document-to-JSON VLM fine-tuning writeup
- Ubicloud OCR with VLMs

## Current Code Seams

The implementation must use the current semantic-annotation seams, not add a
parallel planner stack.

Core planner seams:

- `lib/semantic_annotations/qwen_gateway.py`
  - active prompt contract
  - profile-specific structured-output handling
  - adaptive multi-image to one-page fallback
- `contracts/schemas/semantic_annotation_model_output.v1.schema.json`
  - current model-facing contract
  - currently caps `pages.maxItems = 4` and `regions.maxItems = 6`
- `contracts/schemas/semantic_annotation_manifest.v1.schema.json`
  - persisted manifest contract
- `lib/semantic_annotations/models.py`
  - typed page/region/domain objects
- `lib/semantic_annotations/docling_context.py`
  - planner-facing Docling context JSON
- `lib/semantic_annotations/docling_audit.py`
  - lexical anchors, suggested family hints, table summaries
- `lib/semantic_annotations/qwen_output_normalization.py`
  - model JSON repair and contract normalization
- `lib/semantic_annotations/policy.py`
  - exact-page-coverage and semantic-region validity gates
- `lib/semantic_annotations/manifest_merge.py`
  - page-window merge and document-type resolution
- `lib/semantic_annotations/service.py`
  - Granite enqueue selection and current Smart Parse fanout cap
- `lib/semantic_annotations/schema_fit.py`
  - schema-fit downgrade rules before Granite extraction
- `scripts/gpu/run_phase8_5_semantic_canary.py`
  - semantic-only canary harness and token-budget reporting

Persistence seams:

- `database/075_phase8_5_semantic_annotations.sql`
- `database/077_phase8_5_semantic_type_constraint.sql`
- `database/080_phase8_5_semantic_type_expansion.sql`
- `lib/semantic_annotations/repository.py`

The repo already has a semantic-annotation persistence path. The new planner
fields should stay in `manifest_json`, `confidence_json`, and per-row
`metadata_json` unless there is a proven need for first-class indexed columns.
That keeps this pass additive and low-regression.

## Required Planner Behavior

### 1. High Recall, Still Bounded

Smart Parse should prefer "all materially extractable regions" over "top few
regions."

Required behavior:

- emit every materially useful extraction target that could change downstream
  factual coverage;
- keep boilerplate/no-target regions explicit when they clarify why a page was
  skipped;
- do not emit every visible field or attempt extraction;
- cap regions per page, not only per document, so multi-page documents do not
  lose continuation/service/payment regions.

Target default bound:

- maximum 12 regions per request
- soft prompt rule: no more than 3 materially extractable regions per page
- repeated header/boilerplate regions should be deduped before Granite fanout

### 2. Inventory Before Routing

Qwen should behave as if it does two jobs even if the first implementation uses
one model call:

1. inventory the document's useful pages, sections, tables, and continuation
   structure;
2. choose Granite-worthy extraction targets from that inventory.

The planner prompt should explicitly instruct the model to account for all pages
before selecting extraction targets.

### 3. Grounded, Non-Canonical Output

Qwen must continue to avoid canonical facts.

It may output:

- document family hypotheses
- page roles and usefulness
- region types and extraction priority
- expected field names
- routing reasons
- continuation grouping
- weak-signal warnings
- optional coarse visual hints

It may not output:

- invoice totals
- payment values
- customer names
- dates
- canonical facts
- fabricated coordinates that bypass Docling IDs

### 4. Unsupported Documents Must Stay Honest

When schema fit is weak, Qwen must route to:

- `document_observation`
- `generic_form`
- `unsupported_document`
- `no_extraction_target`

It must not coerce escrow/title/dispute/other forms into invoice, receipt, or
medical EOB just to satisfy a known schema.

## Contract Changes

The semantic contracts should remain `v1` and expand additively.

### Document-Level Additions

Keep existing required fields and add optional planner telemetry:

- `document_type_candidates`
  - array, max 4
  - each item: `document_type`, `confidence`, `evidence_terms`, `reason`
- `planner_notes`
  - array, max 6 short strings
  - for canary/debug visibility only

These fields should be optional and ignored safely by older readers.

### Page-Level Additions

Keep current required fields and add optional fields:

- `page_family_hints`: array max 3
- `continuation_group`: string or null
- `docling_table_signal`: `none | weak | strong | unknown`
- `requires_cross_page_context`: boolean
- `material_region_count_hint`: integer or null

Rationale:

- multi-page service invoices and orders need continuity hints
- weak or empty Docling table markdown should be visible to downstream routing
- page-level cross-page dependence should survive the one-page fallback path

### Region-Level Additions

Keep current required fields and add the following optional fields:

- `importance`: `low | medium | high | critical`
- `source_signal`: `text | table | visual | mixed`
- `coverage_role`:
  `primary | continuation | summary | supporting | boilerplate | unknown`
- `extraction_scope`:
  `table | element | page | multi_page_group`
- `requires_full_page_image`: boolean
- `continuation_group`: string or null
- `must_extract_reason`: string or null
- `negative_routing_reason`: string or null
- `min_expected_items`: integer or null
- `visual_bbox_hint`: optional object with `x1`, `y1`, `x2`, `y2` on the
  0-1000 normalized scale

Rules:

- `visual_bbox_hint` is advisory only and never replaces Docling grounding
- `must_extract_reason` explains why the region matters
- `negative_routing_reason` explains why a plausible region was downgraded
- `min_expected_items` is useful for tables and service-line continuation pages

### Schema Shape Constraints

To preserve vLLM structured-output reliability:

- keep schemas shallow
- avoid deep nesting and complex `$ref` chains
- keep arrays bounded
- keep strings short and sentence-like
- keep nullable fields explicit
- keep optional planner telemetry separate from required routing fields

## Prompt Contract Changes

The prompt contract must be rewritten around these rules:

1. "Emit all materially extractable regions; bounded recall is preferred over
   sparse omission."
2. "First account for every page image, then select grounded extraction
   targets."
3. "Do not output field values or canonical facts."
4. "Use Docling `page_id`, `element_id`, and `table_id` whenever possible."
5. "If Docling table signal is weak but the page visually contains a table or
   line-item structure, mark that explicitly and still emit the region."
6. "Do not force unsupported document families into invoice, receipt, or
   medical EOB."
7. "Preserve continuation groups across pages."

Few-shot examples should be added for:

- BMW service invoice / service record
- BH Photo retail order
- MRI Anthem denial / medical denial
- title seller information form
- escrow statement
- generic low-signal scan

Few-shot examples should be compact and show planner shape, not extraction
payloads.

## Docling Context Changes

The current Docling context seam is fundamentally sound, but the planner needs a
slightly richer whole-document prelude and slightly more explicit weak-signal
markers.

Required additions to `build_docling_context()`:

- page-outline first and last page emphasis
- lexical-anchor counts, not only terms
- explicit weak-table markers when `table_markdown` is empty but table objects
  exist
- explicit page heading or top-snippet emphasis where available
- document-level "family tension" clues when Docling anchors point in multiple
  directions

Important constraint:

- do not reintroduce large bbox arrays or page-image hashes into the Qwen
  prompt path
- keep Qwen planner images at planner resolution only
- do not weaken Granite page/crop/table inputs

## Merge, Policy, And Fanout Rules

### Document Type Merge

`merge_partial_manifests()` should keep weighted voting, but the winning family
decision should be explainable and degrade safely when evidence conflicts.

Required behavior:

- keep competing document-family votes
- prefer Docling anchors over weak page-only hints
- degrade to `generic_form` or `unsupported_document` when evidence remains
  conflicted
- keep resolution telemetry in `confidence_json`

### Region Dedupe

Repeated header or summary regions should not consume the entire Granite budget.

Required dedupe policy:

- dedupe same semantic type plus same grounding
- dedupe repeated header/boilerplate on continuation pages
- preserve distinct summary versus line-item regions

### Planner Recall Versus Granite Budget

Qwen recall and Granite execution budget must be separated.

Required behavior:

- planner may emit up to 12 regions
- Smart Parse Granite execution should select the best bounded subset after
  dedupe and schema-fit gating
- service-line, line-item, and payment-summary regions must not be dropped
  behind repeated headers or low-value boilerplate

The existing Smart Parse Granite cap of 4 should be revisited in the same pass.
The likely target is:

- planner output cap: 12
- Smart Parse Granite enqueue cap: 6

If the cap stays lower, the selection policy must explicitly protect line-item
and payment regions over repeated headers.

## Persistence Strategy

Prefer additive metadata over new columns.

Required persistence behavior:

- persisted manifests store new planner fields in `manifest_json`
- `page_semantic_annotations.metadata_json` stores new page-level planner fields
- `semantic_region_annotations.metadata_json` stores new region-level planner
  fields unless a future query need proves a first-class column is necessary
- if a new semantic type or page role is added to a runtime contract, matching
  DB constraints must be updated in the same change set

## Verification Strategy

This pass needs a semantic-only canary before any new Granite tuning.

### Canary Assertions

For each canary document, the harness should support:

- expected or allowed document families
- forbidden masquerades
- minimum page coverage
- minimum material region count
- required semantic types
- required continuation groups when applicable
- required weak-table warnings when Docling table signal is empty/weak

BMW-specific expectations:

- service or service-record family allowed
- at least one line-item table region on page 1 or 2
- at least one continuation/line-item region on page 2
- at least one payment-summary or receipt-payment-summary region
- a weak-table or full-page-image signal if Docling table markdown is weak

### Definition Of Done

This pass is complete only when:

1. Qwen Smart Parse emits a richer, bounded semantic inventory without emitting
   canonical facts.
2. The prompt no longer suppresses materially useful regions by default.
3. Multi-page documents preserve continuation and payment/service boundaries in
   the semantic manifest.
4. Unsupported documents route honestly to observation or unsupported states.
5. Schema additions remain additive and vLLM-friendly.
6. Exact Docling page coverage remains mandatory.
7. Semantic-only canary assertions pass on the private corpus before further
   Granite tuning proceeds.
