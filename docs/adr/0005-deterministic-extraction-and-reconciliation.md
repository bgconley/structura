# ADR 0005: Deterministic Extraction Shapes and Reconciliation

Date: 2026-06-05

## Status

Accepted - incremental implementation in progress

## Context

The Phase 8.5 extraction pipeline (Docling -> Qwen3-VL-8B-FP8 -> Granite 4.0 3B Vision)
cannot reach reliable, repeatable typed output unless the determinism boundary is in
the right place. A previous implementation only *requested* schema-constrained
generation and silently fell back to free-form JSON (`_openai_vision.py`
`allow_structured_output_fallback`), so schema-echo, prose, stray keys, and malformed
JSON reached normalization and were met with an unbounded, ever-growing reject/normalize
rule set. Reconciliation was bespoke per document family over untyped `dict[str, Any]`
payloads (`reconcile_invoice_region_extractions` and siblings;
`FORBIDDEN_CANONICAL_PLACEHOLDERS`), and repeatability was fingerprinted on stochastic
model output. The model cannot be made deterministic; everything after it can.

## Decisions

- **D1 - Determinism boundary.** The model call is the only stochastic stage. Every
  stage after it (normalize, reconcile, project, serialize, fingerprint) is a pure
  function of its inputs. Determinism is guaranteed for *acceptance, reconciliation,
  and output*, never for the model.
- **D2 - Constrained decoding is mandatory.** Every extraction call passes a small,
  flat JSON Schema and uses vLLM guided decoding. The free-form (`json_object`)
  fallback is removed. A structured-output failure is a runtime event: retry once,
  then `pipeline_failed`. Generation never silently degrades to unconstrained output.
- **D3 - One typed Intermediate Representation (`Claim`).** No engine output is
  reconciled in the target schema. Docling KVPs, Granite fields, and line-item rows
  all normalize first into the uniform typed `Claim` record (contract below). The
  current candidate/observation split collapses into this single currency.
- **D4 - Anchor-required, typed-or-dropped.** A value with no concrete Docling anchor
  is not a `Claim`. A value that fails its deterministic typer is dropped or routed to
  review. These two gates replace the placeholder/prompt-echo/schema-artifact reject
  lists; artifacts have no anchor and do not type-check, so they never become Claims.
- **D5 - Shapes are composable fragments, not per-type schemas.** Reusable typed
  primitives (Money, Date, Quantity, Party, Identifier, Address, LineItemRow, Totals)
  compose into families via a declarative registry (data, not code). A new document
  type is a registry entry, not new normalization code. Documents with no matching
  family degrade to a generic anchored-`observations` projection rather than failing.
- **D6 - Reconciliation is one deterministic resolver with explicit precedence.** The
  per-family `reconcile_*` functions are replaced by a single registry-driven resolver
  applying the Source Precedence Matrix below, multi-source agreement, and cross-field
  invariants, emitting a decision + reason code per canonical key.
- **D7 - Output is projected, validated, and fingerprinted from canonical.** One
  deterministic projector per family builds the application JSON from accepted Claims;
  JSON-Schema (Draft 2020-12) validation is a backstop, not a cleaning step.
  Repeatability fingerprints the canonical projection, never raw model tokens; raw
  drift is tracked as a quality signal only.
- **D8 - Quality outcomes are first-class.** `extracted_cleanly`, `needs_human_review`,
  `insufficient_signal`, `no_extraction_target` are persisted decisions emitted by the
  resolver. `pipeline_failed` remains reserved for runtime/system defects.

## Claim IR Field Contract

| Field | Type | Rule |
|---|---|---|
| `claim_id` | string | Deterministic `hash(document_id, anchor, canonical_key, typed_value)` |
| `document_id` | uuid | - |
| `source_engine` | enum | `docling \| granite` - truthful value provenance only; Qwen is planner provenance and may not create Claims |
| `anchor` | object | `{ page, docling_element_ids[], bbox, text_span }` - **REQUIRED**; no anchor => no Claim |
| `canonical_key` | string | From the controlled vocabulary, e.g. `invoice.total_amount` |
| `raw_value` | string | Verbatim model/source value |
| `typed_value` | typed | `Money{amount,currency} \| Date \| Quantity{value,unit} \| Identifier \| Party{name,role} \| Enum \| Text`; must type-check |
| `confidence` | float | Normalized to `[0,1]` |
| `method` | string | Fragment-schema / prompt that produced it |
| `group_id` | string\|null | Binds repeated rows (e.g. line items) into a set |

## Source Precedence Matrix

| Concern | Authority | Rule |
|---|---|---|
| Geometry, reading order, table grid, text spans | **Docling** | Always wins on structure; it is the anchor coordinate system. Qwen/Granite may not assert structure Docling did not see. |
| Semantic type, document family, routing | **Qwen-VL** | Plans/labels/routes, constrained by Docling structure. **Never supplies a canonical value.** |
| Typed field values (money, dates, KVPs, cells) | **Granite** | Canonical only if anchored, type-valid, and conflict-resolved. |
| Value conflicts | deterministic | Precedence `Granite-on-grounded-region > Docling-native-KVP > none`; >=2 sources agreeing => high confidence; cross-field arithmetic can demote a lone inconsistent value to review. |
| Identity / dedupe | deterministic | Fingerprint `(document_id, anchor, canonical_key, typed_value)`; never raw text. |

Invariant: Qwen never wins a value; Docling never loses on structure; Granite never
becomes canonical without an anchor and validation. Lanes do not cross.

## Family Registry Shape (declarative)

```
family:            invoice
required_keys:     [invoice.seller, invoice.total_amount, invoice.invoice_date]
optional_keys:     [invoice.tax_amount, invoice.due_date, invoice.po_number]
fragments:         [Party(role=seller), Party(role=buyer), Money*, Date*, LineItemRow*, TotalsBlock]
cross_field_invariants:
  - sum(line_items.amount) == subtotal
  - subtotal + tax == total
projection_schema: contracts/.../invoice.v1.schema.json   # versioned app contract
```

Resolver decision vocabulary per key: `accepted | needs_review | insufficient_signal |
absent`, each carrying provenance and a machine-readable `reason_code`.

## Consequences

- The placeholder/echo/artifact reject-list maintenance burden disappears; correctness
  comes from constrained generation + the anchor/typing gates.
- Adding a document type is a registry+schema change, not new reconciliation code.
- Repeatability holds: identical Docling structure yields identical canonical JSON and
  identical review decisions, provably, across runs and document types.
- Stage 3-6 become unit-testable pure functions independent of any GPU/model service.
- Existing modules are re-layered, not rewritten: `model_output_normalization` emits
  Claims; `reconciliation.py` becomes the generic resolver; `contract_registry`/
  `schema_registry` host fragments+families; `reliability_fingerprints` targets the
  canonical projection.

## Implementation Progress

- 2026-06-05: D2 is implemented for the shared OpenAI-compatible vision adapter.
  `VisionGenerateRequest.allow_structured_output_fallback` and the free-form
  `json_object` retry path were removed; structured-output failures now fail closed as
  model protocol/runtime errors for the job layer to retry or dead-letter.
- 2026-06-05: Invoice semantic-region reconciliation first moved from raw
  `normalized_json` payloads to persisted `RegionExtractionEnvelope` facts and line
  items. This was a temporary compatibility bridge toward D3/D6, not the final
  `Claim` IR or generic resolver.
- 2026-06-05: The first `Claim` IR module is implemented in `lib/extraction/claims.py`.
  It emits deterministic claim IDs from `(document_id, anchor, canonical_key,
  typed_value)`, drops unanchored values, normalizes Granite provenance to `granite`,
  and converts region-envelope facts and line items into anchored typed claims.
- 2026-06-05: Invoice semantic-region reconciliation moved again to explicit Claims,
  ahead of both region envelopes and raw normalized payloads.
- 2026-06-05: `lib/extraction/claim_resolver.py` introduces the first registry-driven
  deterministic resolver seam. Invoice Claims are projected through registry entries for
  invoice fields and line-item fragments, conflicts use explicit source precedence, and
  invoice semantic-region reconciliation now consumes this resolver instead of local
  Claim-key merge branches.
- 2026-06-05: Receipt Claims now use family-specific `receipt.line_item.*` keys and
  resolve through the same claim resolver registry. Receipt field projections cover
  merchant and transaction facts, while receipt line-item fragments project through
  registry data rather than bespoke receipt code. The receipt line-item projection
  stays within `receipt.v1` instead of importing invoice-only tax fields.
- 2026-06-05: Unsupported or review-only Claim families now degrade through the
  resolver to `document_observation` projections. Anchored Claims are conflict-resolved
  with the same source-precedence decisions, then emitted as review-only observations
  instead of requiring a new per-family reconciliation function or failing at registry
  lookup time.
- 2026-06-05: Semantic-region aggregate persistence now supports
  `document_observation` in addition to invoice. Observation aggregates are built only
  from anchored Claims, validated against `document_observation.v1`, and persisted with
  observation candidates; raw unanchored region `normalized_json` remains excluded from
  the aggregate path.
- 2026-06-05: Invoice semantic-region aggregation now requires Claims. Raw invoice
  dicts, envelope-only facts/line items, legacy fallback flags,
  `FORBIDDEN_CANONICAL_PLACEHOLDERS`, and `semantic_type.endswith(...)` raw routing
  were removed from invoice reconciliation; raw region `normalized_json` is retained
  only as lineage/debug payload, not as reconciliation input.
- 2026-06-05: Medical EOB Claims now resolve through the family registry and
  semantic-region aggregate persistence supports `medical_eob`. EOB aggregates are
  projected from anchored Claims into payer, patient, claim, financial summary, and
  service-line contract fields while contradictory raw region `normalized_json` remains
  outside the aggregate path.
- 2026-06-05: Repeatability fingerprinting for `canonicalOutput` now hashes a
  deterministic canonical projection of field, line-item, and observation values
  instead of full runtime candidate rows. Candidate lineage, model schema names,
  confidence drift, source engine, and candidate fingerprints remain separate runtime
  quality/lineage signals rather than canonical-output identity.
- 2026-06-05: The Claim resolver now emits first-class Phase 8.5 quality outcomes:
  `extracted_cleanly`, `needs_human_review`, `insufficient_signal`,
  `no_extraction_target`, and `pipeline_failed`. Claim-backed invoice, medical EOB,
  and document-observation aggregates persist the resolver outcome in metadata, so
  document-quality uncertainty is represented as review/quality state rather than an
  operational pipeline failure.
- 2026-06-05: Claim family registry data moved to
  `lib/extraction/claim_registry.py` and expanded beyond invoice, receipt, and
  medical EOB to service records and retail orders. Receipt-compatible Granite
  routes now preserve canonical `service_record.*` and `retail_order.*` Claim keys
  instead of collapsing them into receipt keys, and service/retail canonical targets
  without first-class app schemas reconcile into review-only `document_observation`
  aggregates with source-schema metadata.
- 2026-06-05: Candidate admission now treats service-record and retail-order
  canonical targets as observation-only until first-class app schemas exist.
  Receipt-compatible model contracts may still be used for extraction, but
  receipt-prefixed field and line-item candidates are rejected at the admission
  boundary instead of being persisted as canonical receipt candidates.
- 2026-06-05: The shared OpenAI-compatible vision adapter now requires every
  vision generation request to include a JSON Schema before it will call the
  model transport. The last manual Phase 8.5 GPU live-probe `json_object`
  request was replaced with a strict `json_schema` probe payload, so
  free-form JSON is no longer a permitted runtime path for vision generation.
- 2026-06-05: `VisionGenerateRequest` no longer exposes a
  `structured_output_mode` switch. The shared OpenAI-compatible vision adapter
  always sends strict `response_format: json_schema`, removing the last
  adapter-level route to alternate structured-output mechanisms.
- 2026-06-05: Invoice semantic-region aggregation no longer accepts
  document-level raw `normalized_json` fallback fields. The repository stopped
  loading current document-level Granite output as aggregate fallback, and
  `reconcile_invoice_region_extractions` now derives invoice identifiers,
  dates, totals, and line items only from anchored Claims plus deterministic
  metadata.
- 2026-06-05: Shared Claim-region aggregate assembly now lives in
  `lib/extraction/claim_aggregate_reconciliation.py`. Medical EOB and
  document-observation aggregate wrappers use this shared path for Claim
  collection, region audit metadata, resolver decisions, quality outcome, and
  source-family metadata derived from Claim canonical keys instead of raw
  region `normalized_json`.
- 2026-06-05: Invoice source-family compatibility also moved to Claim-derived
  canonical-key families. A misleading raw region `schema_name` can no longer
  reject otherwise valid invoice Claims or mark non-invoice Claims as invoice
  aggregate input.
- 2026-06-05: Shared Claim-region aggregate assembly now enforces Claim-family
  compatibility for first-class aggregate projections. Incompatible Claim
  families are skipped with `aggregate_incompatible_source_family` metadata,
  while `document_observation` remains the review-only path that can collect
  arbitrary anchored Claim families.
- 2026-06-05: Invoice semantic-region aggregation now uses the same shared
  Claim-region aggregate assembly as medical EOB and document observations.
  Invoice-specific formatting still owns seller checks, payment-summary
  metadata, missing-field warnings, and line-item dedupe, while Claim
  collection, family compatibility, resolver decisions, and quality outcome
  come from the shared path.
- 2026-06-05: Qwen-sourced evidence is no longer allowed to construct typed
  Claims. Qwen remains the semantic planner/router, while value Claims must
  come from Docling or Granite evidence so Qwen annotations cannot become
  canonical facts by provenance drift.
- 2026-06-05: Claim family registries now declare required value keys and the
  resolver emits explicit `absent` decisions with `required_claim_absent`
  reasons when no usable Docling/Granite Claim exists. Partial first-class
  projections with required Claim gaps are marked `needs_human_review` instead
  of `extracted_cleanly`, while empty projections remain `insufficient_signal`.
- 2026-06-05: Claim admission is now controlled by the family registry for
  registered first-class families. Unknown keys such as schema echoes under
  `invoice.*`, `receipt.*`, or `medical_eob.*` are dropped before becoming
  Claims, while unregistered families remain admissible for review-only
  `document_observation` fallback.
- 2026-06-05: Registered Claim fields and line-item suffixes now declare
  acceptable typed primitives in the family registry. Claim admission rejects
  wrong-type values such as text emitted for `invoice.total_amount`, preserving
  the typed-or-dropped boundary before resolver projection.
- 2026-06-05: The Claim resolver now applies registered arithmetic invariants.
  Invoice `subtotal + tax_total == total_amount` is checked after source
  precedence selection, and a selected inconsistent total is demoted to
  `needs_review` with `cross_field_arithmetic_conflict`.
- 2026-06-05: Money invariants now also check explicit currency consistency.
  A numerically balanced invoice total is still demoted to `needs_review` with
  `cross_field_currency_conflict` when the selected subtotal, tax, and total
  Claims use conflicting currencies.
- 2026-06-05: Claim invariant evaluation moved into
  `lib/extraction/claim_invariants.py`, and invoice line-item rollups are now
  checked deterministically. A selected subtotal is demoted to `needs_review`
  with `line_item_sum_conflict` when it disagrees with the resolved sum of
  invoice line-item amounts.
- 2026-06-05: Receipt total arithmetic now uses the same registered Claim
  invariant path as invoices. `receipt.transaction.total` is demoted to
  `needs_review` with `cross_field_arithmetic_conflict` when the selected
  subtotal, tax, and tip Claims do not reconcile.
- 2026-06-05: Receipt line-item rollups now also use the shared Claim
  invariant path. A selected `receipt.transaction.subtotal` is demoted to
  `needs_review` with `line_item_sum_conflict` when it disagrees with the
  resolved sum of receipt line-item amounts.
- 2026-06-05: Receipt now declares `receipt.transaction.total` as a required
  Claim key. Line-item-only receipt projections record an explicit `absent`
  / `required_claim_absent` decision instead of being marked clean.
- 2026-06-05: Medical EOB now declares payer and patient display names as
  required Claim keys, mirroring the existing validator presence checks. EOB
  service-line-only projections retain useful service evidence but stay
  `needs_human_review` with explicit required-party absence decisions.
- 2026-06-05: Medical EOB service-line Claims now preserve allowed and
  plan-paid amounts from Granite's constrained service-line contract. The
  normalized payload, region envelope, Claim IR, and resolver registry all
  carry these anchored values into `medical_eob.v1` line-item projection
  instead of dropping them before reconciliation.
- 2026-06-05: Medical EOB financial-summary plausibility now runs through
  the shared Claim invariant evaluator. When total plan paid plus total
  patient responsibility exceeds total allowed beyond the two-cent validator
  tolerance, `medical_eob.total_allowed` is demoted to `needs_review` with
  `cross_field_plausibility_conflict`.
- 2026-06-05: Invoice total adjustments now flow through the constrained
  Granite line-item schema, normalization, region envelope facts, Claim
  admission, and resolver registry. `invoice.shipping_total` and
  `invoice.discount_total` are projected into `invoice.v1` totals, and invoice
  total arithmetic now evaluates subtotal plus tax plus shipping minus discount.
- 2026-06-05: Receipt discounts now flow through the constrained Granite
  payment-summary schema, normalization, region envelope facts, Claim
  admission, and resolver registry. `receipt.transaction.discount_total` is
  projected into `receipt.v1` and receipt total arithmetic now subtracts the
  discount from subtotal plus tax plus tip.
- 2026-06-05: Receipt line-item fragments now preserve unit-level discount and
  tax/category hints through the constrained Granite line-item schema,
  normalization, region envelope facts, Claim IR, candidate identity, and
  resolver registry.
- 2026-06-05: Service-record line items now preserve labor-operation and
  part-number codes through receipt-shaped alias normalization, region envelope
  facts, and canonical `service_record.line_item.code` Claims instead of
  dropping those identifiers before deterministic projection.
- 2026-06-05: Receipt-shaped alias header facts now respect the resolved
  canonical family. Retail-order model outputs emit anchored
  `retail_order.merchant_name`, `retail_order.order_number`,
  `retail_order.order_date`, and `retail_order.total` Claims, while
  service-record totals emit `service_record.*` Claims instead of leaking
  receipt-prefixed header facts into alias reconciliation.
- 2026-06-05: Region aggregate reconciliation inputs no longer carry raw
  `normalized_json`. The repository loader selects only region identity and
  normalization-envelope lineage, and `RegionExtraction` now exposes only
  optional region envelopes plus typed Claims, keeping raw model payloads out
  of deterministic reconciliation.
- 2026-06-05: Semantic-region candidate creation now derives field,
  line-item, and observation candidates from typed Claims instead of
  round-tripping `RegionExtractionEnvelope` data through legacy normalized
  target-schema payload parsing. Stored normalized projections remain lineage
  data, while candidate creation uses the Claim registry and resolver path.
- 2026-06-05: Candidate admission no longer runs legacy target-payload
  rejection scans for semantic-region extractions that carry a
  `RegionExtractionEnvelope`. Claim-backed semantic-region candidates are the
  admission input; normalized projections remain debug/lineage data instead of
  a second reject-list surface.
- 2026-06-05: Semantic-region validation evidence checks now read from
  admissible typed Claims in the `RegionExtractionEnvelope` instead of the
  stored normalized projection. This keeps evidence health aligned with the
  same Claim-backed path used for candidate creation and admission while
  preserving normalized projections as debug/lineage data only.
- 2026-06-05: Claim family registries now carry aggregate projection metadata
  for first-class families, and Medical EOB aggregate JSON is built through the
  shared registry-driven Claim projector instead of bespoke container and
  service-line dict assembly. This starts moving app-payload projection toward
  declarative family registry data while preserving the existing schema shape.
- 2026-06-05: Invoice aggregate JSON now also uses the shared registry-driven
  Claim projector for invoice, totals, and line-item shape. Invoice-specific
  policy remains in the invoice wrapper only for external seller context,
  payment-summary metadata, missing-field review warnings, and duplicate line
  row selection.
- 2026-06-05: Document-observation aggregate JSON now uses the shared Claim
  projection module for generic anchored observations. The observation
  reconciler is limited to Claim-region resolution while the projector
  preserves the existing `document_observation.v1` payload shape.
- 2026-06-06: OpenAI-compatible vision requests now sanitize only the
  `response_format.json_schema.name` transport field to the documented
  structured-output character and length constraints. Canonical Structura
  schema names such as `granite_invoice_line_items.v1` remain preserved in
  metadata, model-output schema lineage, validation, and reconciliation.
- 2026-06-06: Docling structural-target priority now uses the explicit
  `LINE_ITEM_TABLE_SEMANTIC_TYPES` registry instead of inferring table-critical
  routing from a `semantic_type.endswith(...)` suffix check.
- 2026-06-06: Model-output contracts are now loaded by `ContractRegistry` and
  enforced by `scripts/validate_contracts.py` as strict structured-output
  schemas. Granite fragment schemas close every object with
  `additionalProperties: false`, bound confidence to finite numeric keys, and
  keep generic KVP/fact values scalar instead of allowing arbitrary object or
  array payloads from the model.
- 2026-06-06: Repeatability `candidateFingerprints` now hashes admitted
  candidates only, while preserving legacy undecided report rows. Explicitly
  rejected prompt/schema/placeholder noise is represented by the rejection
  distribution gate instead of causing canonical repeatability drift.
- 2026-06-06: Model-output wrapper normalization no longer converts scalar or
  list payloads into synthetic `raw_text`/`item_N` observation fields. Non-object
  model payloads are dropped with explicit repair metadata; live strict
  structured-output clients should fail such payloads before normalization.
- 2026-06-06: Model-output normalization no longer unwraps object envelopes such
  as `{"data": ...}` or `{"normalized": ...}`. Contracted model-output schemas
  are the direct payload shape; wrapper objects remain off-contract fields for
  schema validation/admission instead of becoming a downstream repair path.
- 2026-06-06: Flat, corpus-specific line-item repair paths were removed for
  invoice and service-record outputs. Granite line-item fragments must use the
  contracted top-level `line_items` array; flat arrays such as
  `service_description`, `parts`, `labor_cost`, `part_number`, and `line_total`
  are rejected as off-contract top-level fields instead of being mined for
  candidates or Claims.
- 2026-06-06: Line-item admission is now schema-aware at the item level.
  Invoice, receipt, retail-order, and service-record fragments each admit only
  the keys declared by their selected model-output contract, so service-record
  aliases such as `service_description`, `service_cost`, `line_total`, or
  `labor_operation` cannot leak into invoice/receipt normalization unless the
  selected contract explicitly allows them.
- 2026-06-06: The remaining top-level `invoice_line_items` alias was removed.
  Line-item fragment normalization now admits only the contracted top-level
  `line_items` key, leaving alias-shaped payloads as rejected off-contract
  input instead of a compatibility path.
- 2026-06-06: Generic KVP observation normalization no longer maps arbitrary
  flat top-level fields into observations. `granite_generic_kvp.v1` must use
  its contracted `fields` array, while direct-field observation contracts keep
  their declared top-level keys.
- 2026-06-06: Direct-field observation contracts now admit only their declared
  top-level fields. Unknown keys in seller-info, mortgage-escrow, or dispute
  model outputs are rejected as off-contract input instead of passing through
  a prompt/schema echo deny list.
- 2026-06-06: Direct-field observation admission now derives those declared
  top-level fields from the selected model-output schema contract instead of a
  second hard-coded allow-list. Generic KVP remains a separate contracted
  `fields`-array shape.
- 2026-06-06: Uncontracted document-observation model payloads now fail closed
  at normalization: arbitrary flat fields are rejected, and generic fallback
  must be represented by the explicit `granite_generic_kvp.v1` `fields` array.
- 2026-06-06: Observation rejected-field metadata now treats `fields` as accepted
  only for `granite_generic_kvp.v1`; direct-field observation contracts report
  a stray `fields` array as rejected instead of silently dropping it.
- 2026-06-06: The live extraction routing gateway no longer imports, accepts,
  constructs, or branches to a Qwen extraction gateway. Qwen remains a semantic
  planner only; disabled Qwen extraction routes fail closed before model use.
- 2026-06-06: Model-backed semantic-region extractions without a
  `RegionExtractionEnvelope` no longer fall through to legacy target-payload
  candidate creation. Candidates are suppressed and normalization metadata marks
  the missing envelope so semantic-region candidates stay Claim/envelope-backed.
- 2026-06-06: Live Granite routing now requires a grounded semantic-region
  extraction task. Broad document-level structured-schema requests fail closed
  before model use, so live extraction cannot ask Granite to extract an entire
  invoice, receipt, or EOB without Qwen/Docling grounded region planning.
- 2026-06-06: The Granite extraction adapter itself now enforces the same
  grounded semantic-region requirement. Direct adapter callers cannot bypass
  routing policy and invoke broad document-level Granite extraction.

## Deferred Work

- Plan-stage stochasticity (Qwen routing variance) is bounded by greedy/low-temperature
  decoding, Docling-anchored region identity, and treating plan drift as a quality
  signal; a fully deterministic plan is out of scope.
- Remaining migration order (highest leverage first): (1) keep expanding the resolver
  registry while retiring any remaining non-Claim compatibility paths; (2) refactor
  schemas into fragments+registry.
