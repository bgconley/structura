# ADR 0006: Extractive-First Extraction Architecture

Date: 2026-06-10

## Status

Accepted - supersedes the generative-extraction value path planned in
ADR 0004/Phase 8.5; preserves and builds on ADR 0005.

## Context

The Phase 8.5 pipeline extracts canonical values by rendering page images and
asking a small vision model (Granite 4.0 3B) to *transcribe* them into
schema-constrained JSON, even when Docling already holds the exact text,
table cells, and coordinates losslessly. The consequences, observed across
nine instrumented corpus runs (20260610T011723Z through 20260610T070545Z):

- Generative transcription failure classes: schema echo, fabricated values,
  money-locale ambiguity, percent-style confidences, output truncation, and
  finally grammar-level degeneration (truncation diagnostics showed 45k-68k
  characters of whitespace around three JSON tokens). Each was individually
  fixed (budgets, grammar bounds, `disable_any_whitespace`), but the class
  exists because values pass through a small model's token stream at all.
- The anchor system runs backwards: `docling_anchor_resolution.py` string-
  searches model output back into Docling text to discover where values came
  from — data the system already possessed.
- Plan stochasticity: Qwen's region plan is sampled, so coverage varies run
  to run, and a planner dead-letter kills the document's extraction entirely.
- Roughly nine representations per value (model JSON -> contract ->
  normalization -> envelope -> claims -> decisions -> projection ->
  candidates -> canonical); the 2026-06-09 audit's confirmed findings mapped
  almost one-to-one onto those seams.

`document_tables.table_json` already persists Docling's full cell grid
(per-cell text, bbox, row/col offsets, spans, header flags), and
`document_elements` persists per-element text with bboxes. The lossless
source for most values already exists in the database.

## Decisions

- **X1 - Extractive over generative.** For any region with a usable text
  layer, models *select*; they never transcribe. Values are copied verbatim
  from Docling cells/elements/spans and parsed deterministically. A canonical
  value's anchor is exact by construction because the value originates at the
  anchor.
- **X2 - Two extraction lanes.** The *text lane* (default) extracts from the
  Docling cell grid (tables) and from deterministic candidate spans (KVPs),
  with the model's role limited to column-role labeling and span selection
  through enum-constrained micro-schemas. The *vision lane* (exception)
  handles scans, handwriting, missing/degraded text layers, and text-lane
  abstentions — the documents where vision earns its cost.
- **X3 - One vision model.** The vision lane and all model-assisted labeling
  consolidate on the resident Qwen3-VL-8B-Instruct-FP8 service (text-only
  chat for labeling/selection; image crops with <=10-field micro-schemas for
  difficult documents). The Granite service, gateway, prompting, and budget
  machinery retire once both lanes prefer the text path.
- **X4 - Deterministic-primary planning.** The Docling-derived structural
  plan (tables -> line-item lane, KVP-dense pages -> KVP lane, per the family
  registry) is the plan. Qwen augments it — semantic labels, extra regions,
  page roles, difficulty flags — but may never reduce coverage, and a planner
  failure degrades to the deterministic plan instead of killing the document.
- **X5 - Claims born at extraction.** A claim is created as
  `(anchor, canonical_key, typed_value)` at extraction time. The
  envelope/candidate representations become projections of claims, not
  parallel currencies; the model-output normalization mapping layer retires
  with the generative path.
- **X6 - Per-document orchestration.** Plan -> extract -> resolve ->
  aggregate runs as one job per document (parallelism across documents, not
  across regions with cross-worker rendezvous). The terminal-jobs
  reconciliation trigger, settled-job counting, and advisory-lock machinery
  retire with it.

## What carries over unchanged

- Docling as canonical structure and the anchor coordinate system.
- ADR 0005's deterministic layer: Claim IR, anchor-required/typed-or-dropped,
  family registry, single resolver with precedence and invariants, canonical
  projection/fingerprinting, quality outcomes, review-gated promotion.
- Review policy: model-backed values never auto-promote.

## Source precedence (revised)

| Concern | Authority |
|---|---|
| Structure, anchors, verbatim values | Docling (text lane) |
| Column roles, span selection, semantic labels, difficulty | Model (selection only, enum-constrained) |
| Vision-lane values (scans/handwriting) | Qwen3-VL-8B, review-required, quote-verified where text exists |
| Truth/promotion | Resolver + invariants + human review (unchanged) |

Invariant: in the text lane the model cannot emit a value — selection schemas
are closed enums over deterministic candidates, so transcription failure
classes are unrepresentable.

## Consequences

- Truncation, echo, fabricated values, locale ambiguity, and anchor search
  become structurally impossible in the text lane rather than policed.
- Plans, and therefore coverage and repeatability fingerprints, are
  deterministic; model variance is confined to labels and the vision lane.
- One fewer model service on the two 24GB cards; VRAM headroom returns.
- The migration is phased (E0-E5, see the 2026-06-10 extractive-first plan);
  each phase is flag-gated and measured against the pinned run-9 corpus
  baseline (20260610T070545Z: 101/101 jobs succeeded, 9 aggregates with
  quality outcomes) before defaults flip.

## Implementation Progress

- 2026-06-10: ADR accepted; migration plan and spec authored
  (docs/superpowers/specs+plans/2026-06-10-extractive-first-extraction-*).
- 2026-06-10: E0+E1 landed behind default-off flags
  (`STRUCTURA_TEXT_LANE_TABLES` / `STRUCTURA_TEXT_LANE_KVP`).
  `lib/extraction/text_lane/` provides the typed `TableGrid` over
  `document_tables.table_json["data"]["grid"]`, lane eligibility
  (line-item semantic type + grounded strong Docling table + clean text
  page), enum column-role labeling on the resident Qwen text endpoint
  (cached by family + header fingerprint), and a verbatim-cell table
  extractor emitting the standard `RegionExtractionEnvelope` with
  docling row anchors, so claims/candidates/reconciliation/review are
  unchanged. Routing falls back to the Granite vision path on
  `TextLaneAbstention` with `normalization_json.lane` telemetry; the
  text lane keeps candidates review-gated in E1. A pre-gate adversarial
  review (25 agents) confirmed and fixed totals-row substring matching,
  leftmost-money totals values, EOB totals double-counting, row_section
  band rows, the flag-less first-row header fallback, the per-job label
  cache, the medical_eob amount gloss, and added money-column sparsity
  abstention for Docling cell loss. GPU A/B gate vs the pinned run-9
  baseline is the next step before defaults flip.
- 2026-06-10: E1 GPU A/B gate passed and `STRUCTURA_TEXT_LANE_TABLES`
  defaults on. Two corpus runs on P620-01
  (20260610T093120Z-text-lane-e1-a, 20260610T095035Z-text-lane-e1-b) vs
  the pinned run-9 baseline: zero dead letters, line-item/field rows >=
  baseline on every document, BMW aggregate observations 10=10,
  evidence-locator completeness 100% for text-lane claims, and the
  text-lane envelopes (line items + totals facts) byte-identical across
  both runs with identical full-corpus canonical fingerprints. The lane
  fired on the BMW service-lines and BH order tables; abstentions worked
  as designed (BH Docling-cell-loss table -> money_columns_sparse ->
  vision; EOB grid -> no_money_column; page-grounded receipt regions ->
  no_grounded_docling_table). Value fidelity: text-lane verbatim amounts
  agree with Granite where Granite was right (127.50) and beat it where
  it wasn't (250.00 vs Granite's 0.0 on the same cell). Two
  baseline-inherited defects were surfaced, not regressed (the
  acceptance evaluator fails run-9's own report identically): aggregate
  admission events carry NULL run_id (ExtractionRunScope.aggregate has
  no run lineage), and rejectedCandidatesInserted collides
  same-field+value identities across engines; both logged for follow-up.
  Also discovered: docling_audit's table signal reads markdown rows plus
  a nonexistent table_json["rows"] key, so it reports every live grid as
  weak — text-lane eligibility derives structure from the parsed grid
  instead, and the audit fix is deferred as its own measured change.
  Next: E2 (extractive KVP lane) and E3 (deterministic-primary planner).
