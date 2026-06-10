# Extractive-First Extraction Migration Plan (E0-E5)

Date: 2026-06-10
Governing decision: `docs/adr/0006-extractive-first-extraction.md`
Preserved foundation: `docs/adr/0005-deterministic-extraction-and-reconciliation.md`
Pinned baseline: corpus run `20260610T070545Z-clean-gate-9` (101/101 jobs
succeeded; 9 current aggregates, all with persisted quality outcomes) over
`/srv/structura/staging/private-corpus/phase85-20260429` (11 documents).

Execution rules (apply to every phase):

- Fresh-context reread before coding a phase: this plan, ADR 0006, ADR 0005,
  and the files named in the phase.
- Each phase lands behind a settings flag, default **off**, with the old path
  intact. The flag flips default-on only after the phase gate passes on the
  GPU node; the old path is removed one phase later at the earliest.
- Phase gate = full unit suite + contracts + a corpus run compared against
  the pinned baseline report (jobs, aggregates, quality outcomes, line-item
  rows/fields, observation candidates, expected-field coverage, repeatability
  across two consecutive runs).
- All evaluation on the GPU node (`bgconley@10.25.0.50`,
  `/tank/repos/structura`) with resident workers; Mac runs are preflight only.

---

## E0 - Text-lane foundation (cell grid + eligibility + flags)

Goal: typed, tested access to the data the text lane consumes; no behavior
change.

1. `lib/extraction/text_lane/__init__.py` (new package).
2. `lib/extraction/text_lane/table_grid.py`: parse
   `ParsedTableText.table_json["data"]["grid"]` into a typed `TableGrid`
   (cells with text/bbox/row/col/spans/header flags; row accessor that
   resolves col/row spans; header-row detection from `column_header` flags
   with first-row fallback). Pure; fixture-tested against grids captured from
   the live corpus (Phenix/BMW/BH shapes).
3. `lib/extraction/text_lane/eligibility.py`: `text_lane_eligibility(source,
   region)` combining `lib/documents/quality.py` page signals (text layer
   present, not handwriting/degraded) and `docling_audit` table signal;
   returns lane + reason (telemetry).
4. Settings (`lib/config/settings.py`): `text_lane_tables_enabled`
   (`STRUCTURA_TEXT_LANE_TABLES`, default false), `text_lane_kvp_enabled`
   (`STRUCTURA_TEXT_LANE_KVP`, default false); map into compose for api +
   worker-extraction + worker-semantic-annotations.
5. Gate: unit suite; grid fixtures round-trip; eligibility classifies the 11
   corpus docs as expected (tables docs -> eligible; the three low-text scans
   -> vision).

## E1 - Extractive table lane (line items)

Goal: line-item claims born from Docling cells; model only labels columns.

1. `lib/extraction/text_lane/column_labeling.py`: build a text-only prompt
   from the header row plus the first 3 data rows; request a micro-schema
   mapping `column_index -> role` where roles are an **enum** of the target
   family's registry line-item fields (from
   `lib/extraction/claim_registry.py`) plus `ignore`. Serve via the existing
   `model-qwen-semantic` OpenAI endpoint (text chat, temperature 0,
   structured outputs already whitespace-disabled). Cache labels by
   `(family, normalized header fingerprint)` in-process; identical tables
   never re-call.
2. `lib/extraction/text_lane/table_extractor.py`: `TableGrid` + column roles
   -> `Claim` records directly: values verbatim from cells, parsed with the
   existing `parse_decimal_text` / `date_value`; anchors =
   `(page_number, table_id, row_index, cell element/bbox)`; `group_id` from
   structural row identity (already supported by `claims.py`);
   `source_engine="docling"`, `method="text_lane_table.v1"`. Totals rows
   (subtotal/tax/total keywords in the description column) emit the family's
   totals claims instead of line items.
3. Routing seam: in the extraction service region execution path
   (`lib/extraction/service.py` + `lib/extraction/gateways/routing.py`):
   line-item-type region AND eligible AND flag on -> text lane (no Granite
   call for that region); otherwise current vision path. The text lane
   produces the same `RegionExtractionEnvelope`+claims persistence shape so
   reconciliation, candidates, resolver, invariants, and review are
   untouched.
4. Telemetry: `normalization_json.lane = "text"|"vision"` + eligibility
   reason; expected-field coverage already records per-region results.
5. Gate (A/B on GPU): with flag on, corpus run vs baseline —
   line-item rows for BMW/BH/receipt docs >= baseline; invoice/receipt totals
   invariants pass rate >= baseline; evidence-locator completeness = 100% for
   text-lane claims; two consecutive runs project byte-identical canonical
   line items for text-lane regions; zero truncation-class events in lane.

## E2 - Extractive KVP lane (span selection)

Goal: KVP/observation claims via deterministic spans + enum selection.

1. `lib/extraction/text_lane/span_candidates.py`: bounded (<=80/page)
   deterministic candidate spans from `source.elements` + page text:
   label-adjacency pairs (same-line `Label: value`, right-of, below-of using
   element bboxes) and typed regexes (money, date, identifiers, phone/zip),
   each carrying `element_id`/`text_span` anchors and a span id.
2. `lib/extraction/text_lane/span_selection.py`: text-only model call mapping
   the region family's expected canonical keys to a **span-id enum** (or
   null). The model cannot output a value. Same endpoint/caching pattern as
   E1.
3. Claims born from selected spans (verbatim text, deterministic typing);
   unmatched keys remain absent (already surfaced by expected-field
   coverage + resolver `required_claim_absent`).
4. Routing: KVP/observation-type regions, eligible + flag on -> KVP text
   lane; else vision path. Touches the same routing seam as E1.
5. Gate: corpus A/B — UWM/Phenix/escrow/title observation candidates and
   aggregate observations >= baseline values with exact anchors; semantic
   canary expectations unchanged or improved; repeatability as in E1.

## E3 - Deterministic-primary planner

Goal: coverage is deterministic; Qwen augments and can no longer kill or
shrink a document's plan.

1. `lib/semantic_annotations/service.py`: build the deterministic baseline
   plan first from `docling_targets.py` (tables -> line-item lane targets,
   KVP-dense pages -> KVP targets, observation families per registry; keep
   the E-series uncapped line-item rescue). Qwen's manifest then *augments*:
   semantic labels attached to baseline regions by grounding match, extra
   regions unioned in, page roles/difficulty/family candidates recorded.
   Final plan invariant: `plan ⊇ deterministic baseline` (assert + telemetry).
2. Planner failure tolerance: semantic-annotation dead-letter no longer
   strands the document — extraction proceeds with the deterministic baseline
   and generic labels; the annotation failure stays a review/ops signal.
   (Removes the 2026-06-10 phase8-live failure mode where one Qwen protocol
   error killed the document.)
3. Plan identity: hash the deterministic baseline into plan/report telemetry;
   repeatability gates compare it across runs.
4. Gate: two consecutive corpus runs produce identical baseline plans and
   identical selected-task sets modulo explicitly-tagged Qwen extras; a
   forced Qwen failure (canary doc) still yields full deterministic coverage.

## E4 - Vision-lane consolidation (retire Granite)

Goal: one vision model, scoped to documents that need vision.

1. Vision lane reimplemented on Qwen3-VL-8B (`model-qwen-semantic`): region
   **crops** (existing visual-input planning), micro-schemas of <=10 fields
   per request emitting `value` + `quote`; where region text exists the quote
   must fuzz-match it or the value is dropped (typed-or-dropped extension);
   for true scans the no-quote mode forces `needs_review` (existing policy).
2. Routing: vision lane only for `quality.py` difficult signals
   (handwriting/scan/low-text) and text-lane abstentions.
3. Retire Granite: remove `model-granite` from compose profiles and bringup,
   `lib/extraction/gateways/granite_vision.py`, `granite_prompting.py`,
   `granite_budgets.py`, granite contracts that have no text-lane consumer,
   and the Granite profile/preflight entries. Reclaim its GPU reservation
   (raise Qwen ctx headroom or co-host text-embed per ops decision).
4. Gate: difficult-document subset (3 scans + handwriting canary) >= current
   baseline quality outcomes; full corpus clean gate; live Playwright
   phase1-8 green.

## E5 - Representation collapse + per-document orchestration

Goal: delete the seams the generative path required.

1. Claims become the persisted currency (extend the envelope persistence or a
   dedicated `extraction_claims` table — decide by read-path measurement);
   region envelope and candidates become projections of claims; retire
   `model_output_normalization` mapping, wrapper/echo scanners, and the
   candidate round-trip paths that exist only for generative output.
2. Per-document orchestration: one `extract` job per document executes
   plan -> lanes (bounded intra-job parallelism for model calls) ->
   resolve -> aggregate inline. Retire `maybe_reconcile_semantic_annotation`
   trigger counting, settled-job exclusion, and advisory locks. Region-level
   queue jobs disappear; queue depth = documents.
3. Gate: corpus clean gate + repeatability; chaos test (kill worker mid-doc)
   shows clean retry semantics; stuck-aggregate class structurally gone.

---

## Sequencing and ownership notes

- E0+E1 first (biggest pain relief, smallest blast radius); E2 next; E3 can
  proceed in parallel with E2 (different seams); E4 only after E1+E2 defaults
  are on; E5 last.
- Anything touching `lib/semantic_annotations/manifest_normalization.py`
  stays structural-only per the generalization spec — E3 does not reintroduce
  family heuristics.
- Wolf logging rules apply per phase (buglog on fixes, memory on sessions,
  ADR 0006 progress entries on landings).
