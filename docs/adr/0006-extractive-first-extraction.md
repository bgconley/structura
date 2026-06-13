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
- 2026-06-10: E2 landed and gated; `STRUCTURA_TEXT_LANE_KVP` defaults on.
  `span_candidates.py` builds bounded deterministic value spans from Docling
  elements (label adjacency over BOTTOMLEFT bboxes + typed regexes,
  positional span ids), `span_selection.py` maps expected keys to a closed
  span-id enum on the resident Qwen text endpoint, and `kvp_extractor.py`
  mints verbatim claims (registry-exact keys -> family facts, others ->
  dot-less observations). A 16-agent pre-gate review confirmed and fixed
  three defects: the money regex matched mid-number, unparseable date spans
  were counted then silently dropped at claim minting, and first-class
  families with non-registry keys minted dead-end dot-less claims while
  suppressing the vision fallback. The first gate run exposed one more
  (MRI denial regions: unregistered resolved family with a first-class
  target dropped all observation candidates) — the abstention now keys on
  the candidate layer's effective family. Gate runs
  20260610T111457Z-text-lane-e2-e / 112154Z-f vs the pinned run-9 baseline:
  Phenix title observations 10->17 and UWM escrow 14->16 with exact
  element/text-span anchors, identical canonical fingerprints across both
  runs, zero dead letters; receipt summaries minted registry facts
  (Scan Sep 9 fields 2->5). Remaining: E3 (deterministic-primary planner),
  E4 (vision-lane consolidation/Granite retirement), E5 (representation
  collapse + per-document orchestration).
- 2026-06-10: E3 landed and gated; `STRUCTURA_DETERMINISTIC_PLANNER`
  defaults on. `lib/semantic_annotations/deterministic_plan.py` builds the
  model-free baseline plan from the docling_targets builders, fingerprints
  it over run-stable structure, and enforces plan ⊇ baseline after Qwen
  augmentation; a Qwen `ModelProtocolError` (the non-retryable class that
  dead-lettered phase8-live) degrades the document to the baseline-only
  plan — persisted as source_engine `docling` under the active qwen
  profile (supersede chain intact), review-required with the failure as
  escalation_reason — while transient timeout/service errors keep the job
  layer's retry-then-recover path. The pre-gate review (17 agents) caught
  the degradation path being dead on arrival (`docling_baseline` not in
  model_source_enum), the profile-name supersede fork, a coverage check
  that let table-grounded Qwen KVP regions suppress deterministic table
  targets, and the over-broad transient catch. Gate runs
  20260610T205327Z-text-lane-e3-g / 210049Z-h: identical baseline
  fingerprints on all 11 documents across two fresh ingests, identical
  canonical-output fingerprints, zero dead letters, and the invariant
  enforcing real coverage Qwen omitted (BH, a receipt scan -> +4
  observations). Live forced-failure canary (qwen URL pointed at a 404):
  baseline manifest persisted, 2 extraction jobs fanned out and succeeded.
  The manifest contract gained the optional `deterministic_baseline`
  telemetry block. Remaining: E4 (vision-lane consolidation / Granite
  retirement; preconditions now satisfied), E5 (representation collapse +
  per-document orchestration).
- 2026-06-13: E4 default-runtime retirement passed the post-flip gate on GPU
  commit `0ce4546`. The Qwen-vs-Granite A/B gate at `aabfb25` first passed for
  the BMW and Anthem difficult-document inputs with identical hard/operational
  acceptance, repeatability fingerprints, and truthful mode lineage. Then the
  default live runtime was rebuilt with Qwen vision fallback enabled, Granite
  removed from required live profiles and `models-live`, and the leftover
  `model-granite` container removed before bringup. Preflight reported three
  required live profiles and healthy `model-qwen-semantic`/`model-vl-embed`;
  `docker compose ps` confirmed `model-granite-not-running`. Resident
  acceptance reports
  `/srv/structura/objects/exports/phase85-runs/e4-default-qwen/20260613T032000Z-e4-default-qwen-0ce4546-pass-1-report.json`
  and `...pass-2-report.json` passed hard correctness, operational SLO,
  report lineage, required summaries, safe outcomes, and repeatability gates.
  Both reports recorded `vision_fallback_provider=qwen`,
  `qwen_vision_fallback_enabled=true`, 13 admitted / 1 rejected candidates,
  zero target dead letters, zero unsafe failures, and identical fingerprints
  (`candidateFingerprints=4565152190f8b7dff7d09e33659591bd875597e1adcb59d0afa43a415a2766da`,
  `canonicalOutput=6b9afd7e2720ce20c60bc622e638c525507ee7323ea91fc3a92b8187d365b074`).
  Remaining: E5 representation/orchestration collapse, including retiring
  legacy `granite_*` model-output/backend labels that are now compatibility
  names rather than default runtime requirements.
- 2026-06-13: The generalization gate now records `documentOutcomes` and
  `documentOutcomeSummary` for every resident-corpus report. Model-backed
  acceptance requires a private holdout or synthetic-adversarial slice, rejects
  holdout documents marked as prompt-tuning inputs, and treats
  `pipeline_failed` as valid only for intentional failure-injection runs or
  real runtime defects. Safe review, insufficient-signal, and no-target
  outcomes remain valid document-quality outcomes rather than job failures.
  Hard invariants also reject missing deterministic-baseline telemetry,
  deterministic-baseline coverage regressions, current aggregate rows without
  source-run lineage, and duplicate current aggregate rows after retry.
