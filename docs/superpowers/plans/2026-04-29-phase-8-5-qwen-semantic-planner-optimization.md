# Phase 8.5 Qwen Semantic Planner Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise Qwen3-VL-4B semantic-planner recall and routing quality so Smart Parse emits a grounded, high-value semantic inventory that survives page-window fallback and drives the right Granite extraction jobs without regressing Phase 8.5 contracts.

**Architecture:** Keep the current Docling -> Qwen semantic manifest -> Granite -> validators/review pipeline. Refactor planner prompting into a focused module, expand semantic contracts additively, enrich Docling context and merge policy, separate planner recall from Granite fanout, and prove behavior through a semantic-only canary before any new Granite tuning.

**Tech Stack:** Python semantic-annotation services, JSON Schema contracts, PostgreSQL semantic annotation persistence, vLLM OpenAI-compatible vision serving, pytest, GPU semantic canary scripts, Firecrawl-backed planning evidence.

---

## Scope

This plan implements
`docs/superpowers/specs/2026-04-29-phase-8-5-qwen-semantic-planner-optimization-spec.md`.

## Implementation Status

Local implementation completed on 2026-04-29. Tasks 1-11 and 13 are implemented
and locally verified. Task 12 remains the GPU semantic canary gate and should be
run before the next full Granite/corpus validation.

Verification completed locally:

- `python -m pytest -q tests/unit/semantic_annotations/test_prompting.py tests/unit/semantic_annotations/test_gateways.py tests/unit/semantic_annotations/test_manifest_merge.py tests/unit/semantic_annotations/test_policy.py tests/unit/semantic_annotations/test_docling_context.py tests/unit/semantic_annotations/test_docling_audit.py tests/unit/semantic_annotations/test_service.py tests/unit/scripts/test_phase8_5_semantic_canary.py tests/unit/test_contract_registry.py tests/integration/test_phase8_5_semantic_annotations.py tests/unit/semantic_annotations/test_target_schema_policy.py tests/unit/extraction/test_semantic_region_routing.py tests/unit/test_migrations.py`
- `python -m ruff check lib/semantic_annotations scripts/gpu tests/unit/semantic_annotations tests/unit/scripts tests/integration/test_phase8_5_semantic_annotations.py tests/unit/extraction/test_semantic_region_routing.py`
- `python -m mypy lib/semantic_annotations scripts/gpu/run_phase8_5_semantic_canary.py`
- `python -m json.tool` over the semantic model-output, semantic manifest, canary
  expectation, and OpenWolf buglog JSON files.

It does not:

- make Qwen output canonical facts
- replace Granite as the extractor
- start Phase 9
- re-enable default or automatic Qwen3-VL-8B behavior
- add new canonical business schemas

## File Structure

These are the planned change seams. Keep responsibilities tight.

### Existing files to modify

- `lib/semantic_annotations/qwen_gateway.py`
  - keep gateway/orchestration
  - remove prompt-contract sprawl from this file
- `contracts/schemas/semantic_annotation_model_output.v1.schema.json`
  - add optional planner fields and new bounds
- `contracts/schemas/semantic_annotation_manifest.v1.schema.json`
  - add matching optional persisted fields
- `lib/semantic_annotations/models.py`
  - add typed optional planner metadata or first-class fields where justified
- `lib/semantic_annotations/docling_context.py`
  - add richer whole-document and weak-table context
- `lib/semantic_annotations/docling_audit.py`
  - expose anchor-count and table-weakness helpers
- `lib/semantic_annotations/qwen_output_normalization.py`
  - accept richer planner output and preserve repairs safely
- `lib/semantic_annotations/policy.py`
  - validate new semantic fields and preserve exact page coverage
- `lib/semantic_annotations/manifest_merge.py`
  - keep competing-family telemetry, continuation handling, and safer downgrade
- `lib/semantic_annotations/service.py`
  - separate planner output budget from Granite enqueue budget
- `lib/semantic_annotations/repository.py`
  - persist metadata cleanly
- `database/080_phase8_5_semantic_type_expansion.sql`
  - extend only if runtime semantic enums exceed current DB constraints
- `scripts/gpu/run_phase8_5_semantic_canary.py`
  - add assertion-driven semantic scoring

### New files to create

- `lib/semantic_annotations/prompting.py`
  - owns semantic prompt assembly, compact few-shot examples, and prompt version
- `tests/unit/semantic_annotations/test_prompting.py`
  - prompt contract regression tests
- `tests/fixtures/semantic_annotations/semantic_canary_expectations.example.json`
  - committed example expectation format
- `docs/superpowers/specs/2026-04-29-phase-8-5-qwen-semantic-planner-optimization-spec.md`
  - this spec

The plan intentionally avoids creating a new planner service or a second
semantic-persistence path.

## Task 1: Lock The Baseline With A Semantic-Only Scorecard

**Files:**
- Modify: `scripts/gpu/run_phase8_5_semantic_canary.py`
- Modify: `tests/unit/scripts/test_phase8_5_semantic_canary.py`
- Create: `tests/fixtures/semantic_annotations/semantic_canary_expectations.example.json`
- Modify: `tests/unit/test_phase8_5_private_corpus_runner.py` only if corpus
  plumbing needs expectation-file support

- [ ] Add expectation-file support to the canary harness so a private local JSON
      file can define:
      - allowed document families
      - forbidden document families
      - minimum region count
      - required semantic types
      - required weak-table signals
      - required continuation groups
- [ ] Extend the report to emit:
      - selected document type
      - competing document-type candidates if present
      - page roles/usefulness
      - region counts by semantic type
      - deduped material-region count
      - weak-table and full-page-image flags
- [ ] Add a committed example expectation file shape, but keep the real private
      corpus expectation file uncommitted.
- [ ] Add unit tests proving the harness:
      - loads expectation JSON
      - reports assertion failures deterministically
      - never enqueues Granite
      - preserves token-budget reporting

Run:

```bash
python -m pytest -q tests/unit/scripts/test_phase8_5_semantic_canary.py tests/unit/test_phase8_5_private_corpus_runner.py
```

Success criteria:

- the harness can fail fast on semantic-quality regressions without touching
  extraction persistence
- report output is specific enough to compare planner revisions across documents

## Task 2: Extract Prompting Out Of `qwen_gateway.py`

**Files:**
- Create: `lib/semantic_annotations/prompting.py`
- Modify: `lib/semantic_annotations/qwen_gateway.py`
- Create: `tests/unit/semantic_annotations/test_prompting.py`
- Modify: `tests/unit/semantic_annotations/test_gateways.py`

- [ ] Move prompt assembly out of `qwen_gateway.py` into a focused
      `prompting.py` module.
- [ ] Keep `qwen_gateway.py` responsible for:
      - profile selection
      - image-window selection
      - client invocation
      - structured-output forwarding
      - fallback orchestration
- [ ] Add prompt unit tests that assert the prompt:
      - says "semantic planner", not extractor
      - forbids canonical facts and field values
      - asks for all materially extractable regions
      - instructs inventory before routing
      - does not tell the model to select only the top few targets
      - does not tell the model to avoid enumerating useful regions
      - preserves Docling-grounded ID usage

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_prompting.py tests/unit/semantic_annotations/test_gateways.py
```

Success criteria:

- the prompt contract is isolated and versionable
- the old sparse-recall wording is removed
- gateway tests still pass with the extracted prompting seam

## Task 3: Rewrite The Planner Prompt For Bounded Recall

**Files:**
- Modify: `lib/semantic_annotations/prompting.py`
- Modify: `lib/semantic_annotations/qwen_gateway.py`
- Modify: `tests/unit/semantic_annotations/test_prompting.py`
- Modify: `tests/unit/semantic_annotations/test_gateways.py`

- [ ] Change the semantic instruction set so Qwen is explicitly recall-oriented:
      - "emit all materially extractable regions"
      - "account for every page before selecting regions"
      - "prefer grounded partial planning over sparse omission"
- [ ] Add compact few-shot planner examples for:
      - BMW service invoice
      - BH retail order
      - medical denial / EOB
      - title seller-information form
      - escrow statement
      - low-signal generic scan
- [ ] Keep examples planner-shaped only:
      - page roles
      - grounded regions
      - expected field names
      - routing reasons
      - no extracted values
- [ ] Keep temperature at `0.0` and structured output enabled.
- [ ] Remove or replace language that tells the model to return only six total
      regions.

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_prompting.py tests/unit/semantic_annotations/test_gateways.py
```

Success criteria:

- the prompt is explicit, compact, and stable
- prompt examples cover the private-corpus hard classes without encoding
  canonical facts

## Task 4: Expand Semantic Contracts Additively

**Files:**
- Modify: `contracts/schemas/semantic_annotation_model_output.v1.schema.json`
- Modify: `contracts/schemas/semantic_annotation_manifest.v1.schema.json`
- Modify: `lib/semantic_annotations/models.py`
- Modify: `lib/semantic_annotations/schema.py`
- Modify: `tests/unit/test_contract_registry.py`
- Modify: `tests/integration/test_phase8_5_semantic_annotations.py`

- [ ] Increase the model-output `regions.maxItems` cap from 6 to 12.
- [ ] Keep `pages.maxItems = 4` because the active Smart Parse fan-in remains
      four images per request.
- [ ] Add optional top-level `document_type_candidates` and `planner_notes`.
- [ ] Add optional page-level fields:
      - `page_family_hints`
      - `continuation_group`
      - `docling_table_signal`
      - `requires_cross_page_context`
      - `material_region_count_hint`
- [ ] Add optional region-level fields:
      - `importance`
      - `source_signal`
      - `coverage_role`
      - `extraction_scope`
      - `requires_full_page_image`
      - `continuation_group`
      - `must_extract_reason`
      - `negative_routing_reason`
      - `min_expected_items`
      - `visual_bbox_hint`
- [ ] Keep all additions shallow and bounded for vLLM structured-output
      reliability.
- [ ] Update typed models so these fields land either as first-class optional
      fields or well-named metadata accessors.

Run:

```bash
python -m pytest -q tests/unit/test_contract_registry.py tests/integration/test_phase8_5_semantic_annotations.py
```

Success criteria:

- existing readers still work
- new fields are optional, bounded, and schema-registered

## Task 5: Enrich Docling Context Without Re-Inflating Prompt Cost

**Files:**
- Modify: `lib/semantic_annotations/docling_context.py`
- Modify: `lib/semantic_annotations/docling_audit.py`
- Modify: `tests/unit/semantic_annotations/test_docling_context.py`
- Modify: `tests/unit/semantic_annotations/test_docling_audit.py`
- Modify: `scripts/gpu/run_phase8_5_semantic_canary.py`

- [ ] Add anchor-count and family-tension visibility to the Docling audit layer.
- [ ] Add explicit weak-table markers when:
      - table objects exist but markdown is empty
      - table markdown is too thin to support routing confidently
- [ ] Enrich the document prelude with:
      - first-page and last-page emphasis
      - stronger page-outline summaries
      - table inventory summaries
      - lexical-anchor counts
- [ ] Keep large bbox arrays and page-image hashes out of the Qwen prompt path.
- [ ] Update the canary token-budget report so the richer prompt still reports:
      - prompt token estimate
      - visual token estimate
      - request window totals

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_docling_context.py tests/unit/semantic_annotations/test_docling_audit.py tests/unit/scripts/test_phase8_5_semantic_canary.py
```

Success criteria:

- Qwen sees more whole-document clues
- prompt growth is measured, not guessed
- Docling weakness is explicit when tables are visually present but text-poor

## Task 6: Harden Normalization For Richer Planner Output

**Files:**
- Modify: `lib/semantic_annotations/qwen_output_normalization.py`
- Modify: `lib/semantic_annotations/policy.py`
- Modify: `tests/unit/semantic_annotations/test_policy.py`
- Modify: `tests/unit/semantic_annotations/test_gateways.py`
- Create or modify focused normalization tests under
  `tests/unit/semantic_annotations/`

- [ ] Accept the new optional planner fields without breaking old payloads.
- [ ] Preserve safe handling for:
      - wrapped page objects
      - wrapped region arrays
      - list/dict/null/string model output
      - duplicate page annotations
      - unmatched regions
- [ ] Record planner repairs and dropped unsupported fields in metadata rather
      than crashing normalization.
- [ ] Validate new bounded enums and fields in `policy.py`.
- [ ] Keep exact Docling page coverage and duplicate-region-intent checks.

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_policy.py tests/unit/semantic_annotations/test_gateways.py tests/integration/test_phase8_5_semantic_annotations.py
```

Success criteria:

- richer planner output remains backward compatible
- malformed or wrapper-heavy model JSON still normalizes safely

## Task 7: Improve Merge And Document-Type Resolution

**Files:**
- Modify: `lib/semantic_annotations/manifest_merge.py`
- Modify: `lib/semantic_annotations/models.py`
- Modify: `tests/unit/semantic_annotations/test_manifest_merge.py`
- Modify: `scripts/gpu/run_phase8_5_semantic_canary.py`

- [ ] Preserve and expose competing document-family votes in the merged
      manifest.
- [ ] Keep Docling anchors heavier than weak page-only hints.
- [ ] When page votes conflict materially, degrade to `generic_form` or
      `unsupported_document` rather than forcing a brittle family choice.
- [ ] Carry continuation-group metadata through page-window merge.
- [ ] Expose merged resolution telemetry in canary reports.

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_manifest_merge.py tests/unit/scripts/test_phase8_5_semantic_canary.py
```

Success criteria:

- multi-page fallback no longer erases cross-page family ambiguity
- document-type decisions are inspectable, not opaque

## Task 8: Separate Planner Recall From Granite Execution Budget

**Files:**
- Modify: `lib/semantic_annotations/service.py`
- Modify: `lib/semantic_annotations/schema_fit.py`
- Modify: `lib/semantic_annotations/target_schema_policy.py`
- Modify: `tests/unit/semantic_annotations/test_service.py`
- Modify: `tests/unit/semantic_annotations/test_target_schema_policy.py`
- Modify: `tests/unit/extraction/test_semantic_region_routing.py`

- [ ] Raise the Smart Parse planner-output ceiling independently from the
      Granite enqueue ceiling.
- [ ] Revisit `MAX_GRANITE_TASKS_BY_QUALITY_MODE["smart"]` from 4 to 6 unless
      targeted tests prove 4 is still sufficient.
- [ ] Add an ordering policy that explicitly protects:
      - line-item/service-table regions
      - payment-summary regions
      - grounded critical/strong-evidence regions
      over repeated headers and low-value boilerplate.
- [ ] Keep schema-fit downgrades before Granite extraction so unsupported forms
      still route to `document_observation`.

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_service.py tests/unit/semantic_annotations/test_target_schema_policy.py tests/unit/extraction/test_semantic_region_routing.py
```

Success criteria:

- improved planner recall is not thrown away before Granite sees it
- unsupported documents still stay honest

## Task 9: Align Persistence And Constraint Drift Safely

**Files:**
- Modify: `lib/semantic_annotations/repository.py`
- Modify: `database/080_phase8_5_semantic_type_expansion.sql` or add a new
  migration only if runtime enums exceed current DB constraints
- Modify: `tests/unit/test_migrations.py`
- Modify: `tests/integration/test_phase8_5_semantic_annotations.py`

- [ ] Persist new page-level and region-level planner data in
      `metadata_json` unless a first-class column is required for query speed or
      API shape.
- [ ] Confirm current DB semantic-type constraints already cover any new runtime
      semantic types.
- [ ] Add a new migration only if the runtime contract expands beyond the
      current `080_phase8_5_semantic_type_expansion.sql` set.
- [ ] Keep this pass additive: no destructive semantic-persistence changes.

Run:

```bash
python -m pytest -q tests/unit/test_migrations.py tests/integration/test_phase8_5_semantic_annotations.py
```

Success criteria:

- runtime contract and DB constraints remain aligned
- no unnecessary schema churn is introduced

## Task 10: Add Document-Specific Semantic Expectations

**Files:**
- Modify: `scripts/gpu/run_phase8_5_semantic_canary.py`
- Modify: `tests/unit/scripts/test_phase8_5_semantic_canary.py`
- Update the private expectation file outside git

- [ ] Define and validate expectation sets for the known canary documents:
      - BMW service invoice
      - BH Photo retail order
      - MRI Anthem denial
      - title/seller form
      - escrow statement
      - generic scans
- [ ] Assert BMW-specific expectations:
      - service/line-item coverage survives
      - payment region survives
      - weak-table/full-page-image signal appears when appropriate
- [ ] Assert forbidden masquerades:
      - title/escrow/dispute docs must not become invoice or medical EOB
      - generic scans must not become fake invoices/EOBs

Run:

```bash
python -m pytest -q tests/unit/scripts/test_phase8_5_semantic_canary.py
```

Success criteria:

- the semantic canary becomes the first gate for planner quality
- document-family drift is caught before Granite tuning

## Task 11: Local Verification

Run the focused local suite before any GPU validation:

```bash
python -m pytest -q \
  tests/unit/semantic_annotations/test_prompting.py \
  tests/unit/semantic_annotations/test_docling_context.py \
  tests/unit/semantic_annotations/test_docling_audit.py \
  tests/unit/semantic_annotations/test_policy.py \
  tests/unit/semantic_annotations/test_gateways.py \
  tests/unit/semantic_annotations/test_manifest_merge.py \
  tests/unit/semantic_annotations/test_target_schema_policy.py \
  tests/unit/semantic_annotations/test_service.py \
  tests/unit/scripts/test_phase8_5_semantic_canary.py \
  tests/integration/test_phase8_5_semantic_annotations.py
```

Optional broader confidence pass before GPU:

```bash
ruff check lib/semantic_annotations scripts/gpu tests/unit/semantic_annotations tests/unit/scripts
python -m mypy lib/semantic_annotations scripts/gpu
python -m pyright
```

## Task 12: GPU Semantic Canary Gate

Run semantic-only canaries on the GPU node before changing Granite behavior
again.

Required first pass:

```bash
python scripts/gpu/run_phase8_5_semantic_canary.py \
  --pdf "/Users/brennanconley/Downloads/BMW CE-04 600mi run in service and tire service 04-23.pdf" \
  --pdf "/Users/brennanconley/Downloads/BH Photo desktop tripod order.pdf" \
  --pdf "/Users/brennanconley/Downloads/MRI Anthem Denial 01-26.pdf" \
  --json-output /srv/structura/objects/exports/phase85-runs/semantic-canary-core.json
```

Required broader private canary:

```bash
python scripts/gpu/run_phase8_5_semantic_canary.py \
  --json-output /srv/structura/objects/exports/phase85-runs/semantic-canary-private.json
```

The GPU gate passes only when:

- exact Docling page coverage remains intact
- expected material region counts are met
- BMW preserves service-line and payment regions
- title/escrow/generic scans do not masquerade as invoice or medical EOB
- planner output is richer without exploding prompt/context budgets

## Task 13: Documentation And Phase 8.5 Plan Alignment

**Files:**
- Modify: `STRUCTURA_PHASE_8_5_SEMANTIC_ANNOTATION_PLAN.md`
- Modify: `STRUCTURA_PHASE_8_5_IMPLEMENTATION_PLAN.md`
- Modify: `agents.md` and `AGENTS.md` only if the canonical planner contract
  or gate language changes materially

- [ ] Update the semantic plan so Smart Parse is described as a high-recall,
      grounded semantic inventory rather than a sparse top-target planner.
- [ ] Update the implementation plan to point at:
      - prompt extraction
      - richer semantic contract
      - semantic canary-first verification
      - separated planner-output versus Granite-execution caps
- [ ] Preserve the anti-pattern rules around Qwen8, Granite truth boundaries,
      and runtime/system versus document-quality failures.

## Stop Point

Stop after the semantic canary is passing and before any new Granite prompt or
schema tuning. The next phase after this plan is a new Granite-focused pass that
uses the improved planner output as its input surface.
