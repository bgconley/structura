# Phase 8.5 Qwen Semantic Understanding Generalization Spec

## Purpose

This spec defines the next Phase 8.5 Qwen3-VL-4B pass: preserve and expand the
high-recall, evidence-grounded semantic document-understanding layer while
removing drift toward document-instance hacks or narrow family-specific repair
logic.

The canonical pipeline remains:

```text
Docling physical parse
-> Qwen3-VL-4B semantic document understanding and extraction intent
-> Granite 4.0 3B Vision targeted structured extraction
-> validators / provenance / human review policy
-> canonical facts + evidence/search layer
```

Docling remains the physical truth layer. Qwen3-VL-4B is the semantic
document-understanding layer: it interprets pages, layout, tables, visual/OCR
signals, and cross-page structure; produces a grounded semantic inventory and
extraction intent; and records uncertainty. Granite remains the targeted
structured extractor for candidate data. Validators and review policy remain the
promotion gate.

Qwen must not produce canonical Structura facts, but it is not a minor
classifier. It should use its document parsing, layout, table, position-aware,
OCR, visual, and multi-page capabilities to describe what is materially present
and how downstream extraction should approach it.

This spec supersedes the remaining follow-on work where the earlier optimization
pass began drifting into document-shaped repair behavior.

## Research-Grounded Qwen Role

The research direction is explicit:

1. Qwen3-VL is useful for document parsing, layout understanding, tables,
   position-aware output, OCR-style reading, and multi-page understanding.
2. Structured output should be treated as an API contract: precise schema
   instructions, field rules, examples, validation, and fallback are required.
3. vLLM structured output is useful but not sufficient by itself; validator and
   normalizer safety remains mandatory.
4. Production document pipelines should make model prompts atomic, cited,
   grounded, versioned, and evaluated.
5. Broad "find the important stuff" prompts are brittle; Qwen needs a concrete
   semantic inventory contract.

For Structura, Qwen3-VL-4B should produce:

- every page classified with role and extraction usefulness
- every visually or textually important extraction region, not just the top few
- explicit routing reasons and "why this matters" notes
- table, text, visual, and Docling signal source labels
- whether Docling table text is empty, weak, strong, or unknown
- whether Granite should receive full page, table, element, or crop context
- continuation groups across pages when the document structure supports them
- minimum expected row/item count when obvious from layout
- competing document-family scores instead of one brittle type
- unsupported or generic observations when schema fit is weak

The boundary is equally important: Qwen annotations are semantic observations
and extraction intent. They are not canonical app JSON and they are not promoted
without Granite extraction, validators, evidence policy, and review state.

## Core Judgment

A private-corpus failure such as a missed vehicle-service invoice line-item
region is a representative failure case, not the thing Structura should optimize
for directly.

The right abstraction level is:

- Qwen semantic document-understanding contract
- inventory-before-routing behavior
- richer semantic manifest schema
- whole-document Docling context plus bounded visual fan-in
- grounded extraction-intent output
- structural-only normalization and validation
- semantic-only evaluation gates

The wrong abstraction level is:

- if-this-looks-like-one-document repairs
- family-specific semantic intent injection during normalization
- Qwen output rewriting that exists mainly to make one corpus item pass
- turning Docling audit anchors into a patch table for private documents

## Chosen Direction

We are proceeding with contract-led semantic understanding generalization.

That means:

1. Keep the high-recall Qwen improvements already made.
2. Remove narrow semantic-intent repairs from normalization.
3. Make the Qwen contract inventory-first and route-second.
4. Use document-class examples, not document-instance examples.
5. Treat semantic-only canary scoring as the primary tuning loop before Granite
   or full-pipeline tuning.
6. Preserve Docling as physical truth and Granite as targeted candidate
   extractor.
7. Let validators and review policy decide promotion.

## Anti-Patterns

The following approaches are rejected:

1. Layering narrow heuristics after every private-corpus failure.
   This creates behavior that overfits the corpus and hides business logic in
   normalization.
2. Prompt-only tuning without tests, scorecards, and normalizer guardrails.
   This leaves the same drift path open after the next failure.
3. Presenting a "Qwen is only a planner/classifier" architecture.
   This underuses Qwen3-VL-4B's document-understanding strengths and repeats the
   sparse-routing problem.
4. Making Qwen output canonical app facts directly.
   This bypasses Granite, validators, provenance, and review policy.
5. Adding document-instance prompt rules or repair paths.
   Examples may represent classes, but they must not encode one vendor,
   merchant, patient, account, or document instance.
6. Treating one document family's expected metadata as universal.
   Cross-page continuation, full-page-image routing, and expected row counts
   should be model-emitted semantic observations, not adapter-injected intent.

## Current State To Preserve

These changes are directionally correct and should remain:

1. `phase8_5-semantic-smart-v3` as a recall-oriented Qwen semantic contract
2. `regions.maxItems = 12` instead of the earlier sparse cap
3. semantic-only canary harness and scorecard
4. whole-document Docling context plus page-window filtering
5. adaptive multi-image fallback and 32K runtime headroom
6. structured-output validation and safe normalization
7. per-page and per-region semantic metadata fields

## Current Drift To Remove

These are the behaviors this spec explicitly treats as drift:

1. family-specific semantic metadata repair in
   `lib/semantic_annotations/qwen_output_normalization.py`
2. document-instance few-shot naming such as a specific private-corpus service
   invoice name
3. top-level prompt prose that increasingly encodes one family's routing policy
   instead of broad Qwen semantic behavior
4. canary expectations that imply a single document's exact semantic shape is
   the contract rather than a document-class behavior

## Required Qwen Behavior

### 1. Inventory First, Route Second

Qwen should behave as if it performs two phases even if the implementation stays
single-call for now:

1. page, layout, visual, table, and document inventory
2. grounded extraction routing and extraction-intent selection

The current `pages[]` surface is the mandatory inventory layer.

The current `regions[]` surface is the bounded extraction-intent layer.

Prompt instructions, validation rules, and canary scoring should treat inventory
completeness as a first-class requirement before route quality is judged.

### 2. Require Per-Page Role And Usefulness

For every input page, Qwen must account for:

- `page_role`
- `document_type_hint`
- `extraction_usefulness`
- whether the page is boilerplate or materially useful
- whether the page depends on cross-page context
- whether Docling table signal is `none`, `weak`, `strong`, or `unknown`

Qwen may decide that a page has no extraction target, but it may not silently
skip page accounting.

### 3. Prefer Recall Over Omission

Qwen behavior should prefer too many grounded candidates over omitted material
regions.

That means:

- keep the 12-region cap
- keep a soft per-page budget rather than sparse whole-document routing
- prefer a grounded region that later gets ignored or downgraded over a missing
  line-item, payment, table, denial, statement, or form block
- let Granite enqueue selection and validators trim the candidate set later

### 4. Use Qwen's Visual And Layout Strength

Qwen should inspect and report visual/layout facts that are useful to downstream
extraction, including:

- table-like structures even when Docling table markdown is empty
- row/column grouping hints
- section boundaries and repeated page headers
- cross-page continuations
- visually prominent totals, balances, forms, signatures, denials, receipts, and
  payment blocks
- noncanonical observations when the document is useful but unsupported

This is still not canonical extraction. It is semantic inventory and extraction
intent that helps Granite receive the right task, image scope, and context.

### 5. Keep Grounding Exact

Regions must remain grounded to Docling page, element, or table IDs whenever
possible.

Allowed structural normalization:

- duplicate page collapse
- alternate page-wrapper normalization
- out-of-window page and region filtering
- malformed single-page page-ID repair when the request truly contains one page
- bounded expected-field cleanup

Disallowed semantic-intent normalization:

- injecting continuation groups
- forcing `requires_full_page_image`
- rewriting `semantic_type` because a family heuristic prefers it
- creating synthetic regions that the model did not emit

### 6. Use Document-Class Examples, Not Document Instances

Few-shot examples should remain, but they should be class-based:

- `vehicle_service_invoice`
- `retail_order`
- `medical_denial`
- `title_seller_information_form`
- `escrow_statement`
- `generic_low_signal_form`

Examples should illustrate Qwen output shape:

- page roles
- grounded region families
- expected field names
- routing reasons
- weak-table behavior
- continuation handling
- full-page, table, element, or crop scope selection
- generic observation behavior when canonical schema fit is weak

Examples must not encode vendor, merchant, patient, account, or
instance-specific facts.

### 7. Whole-Document Context Must Stay

The one-page fallback path should continue to receive whole-document Docling
context plus focused image windows.

The page-window adapter should continue to filter model output back to the
requested Docling window before validation.

This is a structural safety mechanism, not a semantic repair layer.

### 8. Keep Schema Fit Honest

Schema fit should remain document-class aware and evidence-based, but it must
not grow into family-specific output rewriting.

Allowed:

- using Docling lexical anchors and family tension as routing evidence
- downgrading weak schema fit to `document_observation`
- preventing escrow, title, dispute, or unsupported forms from masquerading as
  invoice, receipt, or medical EOB

Not allowed:

- post-hoc semantic-type mutation to force a preferred family
- family-specific injection of missing semantic metadata

## Semantic Contract Changes

The existing additive contract expansion is directionally correct. This pass
does not need a new schema version unless implementation reveals an unavoidable
contract break.

### Keep

- `document_type_candidates`
- `planner_notes`
- `page_family_hints`
- `continuation_group`
- `docling_table_signal`
- `requires_cross_page_context`
- `material_region_count_hint`
- `importance`
- `source_signal`
- `coverage_role`
- `extraction_scope`
- `requires_full_page_image`
- `must_extract_reason`
- `negative_routing_reason`
- `min_expected_items`
- `visual_bbox_hint`

### Clarify

The contract meaning should be:

- `pages[]` is the mandatory page/document inventory
- `regions[]` is the bounded extraction-intent proposal
- semantic metadata is model-emitted evidence, not adapter-injected intent
- Qwen may emit rich semantic observations, but Structura owns canonical
  validation, candidate persistence, and promotion

## Docling Context Guidance

Docling should continue to provide:

- whole-document page outline
- first and last page snippets
- table inventory
- weak-table signals
- anchor counts and family tension
- focused page elements and tables

This spec does not require removing document-class lexical anchors entirely.
Document-class audit vocab is acceptable when it is broad, testable, and useful
across multiple documents.

What should stop is using one new failure to justify one new special-case repair
path.

## Evaluation Model

The semantic-only canary remains the primary Qwen iteration gate.

It should score:

1. exact page coverage
2. competing document-family candidates
3. selected document family
4. forbidden masquerade failures
5. per-page role and usefulness coverage
6. minimum region count
7. required semantic region classes
8. weak-table awareness
9. continuation coverage
10. full-page/table/element/crop routing when visually necessary
11. normalization-repair counts
12. fallback frequency and reason

The scorecard should be document-class oriented, not document-instance shaped.

Example:

- it is valid to assert that a multi-page vehicle service invoice class needs
  line-item and payment routing
- it is not valid to assert that one exact service invoice must emit one exact
  metadata repair pattern

## Code Seams To Use

Primary seams:

- `lib/semantic_annotations/prompting.py`
- `lib/semantic_annotations/qwen_gateway.py`
- `lib/semantic_annotations/qwen_output_normalization.py`
- `lib/semantic_annotations/docling_context.py`
- `lib/semantic_annotations/docling_audit.py`
- `lib/semantic_annotations/manifest_merge.py`
- `lib/semantic_annotations/policy.py`
- `lib/semantic_annotations/service.py`
- `scripts/gpu/run_phase8_5_semantic_canary.py`
- `contracts/schemas/semantic_annotation_model_output.v1.schema.json`
- `contracts/schemas/semantic_annotation_manifest.v1.schema.json`

This pass should not create a second semantic pipeline or bypass the existing
repository and persistence seams.

## Definition Of Done

This generalization pass is complete only when:

1. Qwen remains recall-oriented, bounded, and semantically rich
2. page inventory is treated as mandatory and first-class
3. Qwen uses visual/layout/table understanding to report materially useful
   extraction intent
4. semantic-only canary scoring remains the primary Qwen iteration gate
5. narrow family-specific normalization repairs are removed
6. few-shot examples are document-class based, not instance based
7. whole-document context plus focused-page fallback still works
8. schema fit remains evidence-based and honest
9. the private semantic canary improves across multiple document classes without
   adding new document-instance hacks
