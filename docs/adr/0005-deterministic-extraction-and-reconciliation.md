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
- 2026-06-06: Legacy target-payload candidate creation and the final candidate
  admission boundary now reject Qwen-sourced values outright, including
  document-observation candidates. Qwen remains a semantic planner/router only
  even if a compatibility caller returns target-shaped `normalized_json` or
  manually constructed candidates with Qwen provenance.
- 2026-06-06: Concrete evidence checks now treat all normalized model source
  engines as requiring structural anchors. Page-number plus source-text-only
  evidence is no longer concrete for model aliases such as `granite`,
  `model_runtime`, `granite_vision_*`, or historical Qwen profiles.
- 2026-06-06: Candidate admission now applies an even stricter model-value
  anchor rule: semantic-region lineage alone is not enough to admit model
  value candidates. Model-backed fields, line items, and observations need a
  page plus element, table row, bbox, or text-span locator.
- 2026-06-06: The admission boundary now bypasses the legacy raw
  target-payload rejection scanner for all model-backed semantic-region
  extractions, including missing-envelope cases. Semantic-region model output
  is therefore accepted only through typed envelope/Claim-backed candidates;
  raw `normalized_json` remains debug lineage rather than a cleanup surface.
- 2026-06-06: The shared OpenAI-compatible vision adapter now validates the
  returned JSON object against the exact requested response schema before
  returning `structured_output_used=True`. If a model server ignores or weakens
  structured decoding and returns schema-invalid JSON, the adapter fails closed
  with a redacted `ModelProtocolError` instead of handing malformed shape to
  downstream normalizers.
- 2026-06-06: Model-output structured schemas now require at least one
  extraction-bearing root key, and contract validation rejects empty-root
  schemas. This keeps `{}` from being schema-valid model output while still
  allowing honest abstention through empty arrays or nullable fragment fields.
- 2026-06-06: Invoice payment-summary normalization now reads only fields
  declared by `granite_payment_summary.v1`: `invoice_no`, top-level `amount`,
  and declared `payments[]` fields. Legacy aliases such as top-level
  `invoice_number`, nested `invoice`, `totals.amount_paid`, and
  `metadata.payment_summary` remain rejected off-contract payload instead of
  being mined for canonical candidates.
- 2026-06-06: Invoice line-item normalization likewise stopped mining
  top-level `total_amount`; totals now come only from the contracted
  `granite_invoice_line_items.v1` `totals` object.
- 2026-06-06: Granite region normalization now applies a schema-derived
  root-key boundary before mapper-specific logic. Off-contract top-level
  fields are reported as rejected fields and make the selected model-output
  contract fail before mapper input, so aliases cannot be mined even in
  fixture/direct-normalizer paths.
- 2026-06-06: The contract boundary now applies recursively to nested object
  properties and array items only for rejected-field reporting. It no longer
  prunes malformed object records or keeps valid siblings; any invalid registered
  model-output payload fails closed as a whole before mapper logic.
- 2026-06-06: The normalizer contract boundary now validates the original model
  payload against the selected model-output JSON Schema before mapper logic.
  Direct or fixture payloads that contain extra keys, omit required nullable
  fields, or violate type, numeric, length, or array bounds are dropped instead
  of partially mined, with `model_output_contract_errors` and
  `model_output_contract_validation_failed` recorded as lineage metadata. Live
  adapters already fail these payloads before normalization, so this closes the
  compatibility/direct-call path without adding corpus-specific repairs.
- 2026-06-06: Granite structured-output failures now retry once without changing
  the selected JSON Schema contract. Length truncation keeps the existing larger
  budget retry, while schema-invalid JSON, non-object JSON, invalid JSON, or empty
  structured content retries with the same schema and budget before surfacing as a
  model protocol/runtime failure for the job layer. This implements the fail-closed
  `retry once -> pipeline_failed` policy without any `json_object` fallback.
- 2026-06-06: Qwen semantic-planner structured-output failures now use the same
  fail-closed generation policy. Schema-invalid JSON, non-object JSON, invalid JSON,
  empty structured content, and truncation retry once with the same semantic
  annotation schema, prompt, image fan-in, and output budget before surfacing as a
  model protocol failure. Context-length and invalid local schema/configuration
  errors remain non-retryable, and there is still no one-page, high-quality, rescue,
  or `json_object` fallback.
- 2026-06-06: Model-output schemas now enforce OpenAI/vLLM strict structured-output
  object shape recursively: every declared object property is listed in `required`,
  and optional fragment fields use explicit `null` values instead of disappearing
  from the payload shape. The normalizer's direct/fixture compatibility boundary
  now validates those complete shapes as received; it no longer completes
  schema-declared nullable fields to `null`, and it fails closed when
  extraction-bearing roots such as `line_items`, `fields`, or `service_lines` are
  absent or off-contract keys are present.
- 2026-06-06: Semantic annotation and extraction workers now reject stale removed
  high-quality/rescue controls at the queue boundary before service execution.
  Such legacy payloads fail closed as non-retryable contract violations, preserving
  the single Smart Parse Qwen path without creating retry loops or silently ignoring
  removed controls.
- 2026-06-06: Claim resolver precedence no longer uses model confidence as a
  tie-breaker for conflicting Claims. Source authority still wins first, but
  same-source conflicts now select by stable Claim identity and remain
  `needs_review`, preventing stochastic confidence jitter from changing the
  projected review payload.
- 2026-06-06: Claim resolver line-item projection now orders groups by stable
  structural anchor identity instead of model/envelope row order. The same
  Docling-anchored rows therefore project in physical row order even when
  Granite returns line-item fragments in a different sequence.
- 2026-06-06: Line-item Claim group IDs now prefer structural row identity over
  model ordinal when a row-level anchor exists. Duplicate model rows with the
  same Docling table row, element, bbox, or text span collapse into one
  deterministic group, while ordinal remains only a fallback for weaker anchors.
- 2026-06-06: Claim anchors now canonicalize comma-separated Docling element IDs
  before identity hashing. Equivalent Docling anchor sets therefore produce the
  same Claim ID even when provider evidence strings arrive in a different order.
- 2026-06-06: Claim construction now rejects planner-only Qwen semantic methods
  before inspecting facts, line items, or observations. Qwen output therefore
  cannot become value Claims even if a replayed envelope carries concrete-looking
  Docling evidence refs.
- 2026-06-06: Claim source provenance is now method-first. Granite fragment
  methods produce Granite value Claims even when evidence refs describe Docling
  anchor structure, and fallback evidence-source resolution is order-insensitive.
- 2026-06-06: Claim anchor selection now evaluates all structural evidence refs
  instead of trusting list order. The selector prefers richer anchors and then a
  stable page/table/row/json key, so the same evidence set yields the same Claim
  identity even when provider evidence arrays are reordered.
- 2026-06-06: Candidate admission fingerprints now select evidence locators
  deterministically instead of reading `evidence[0]`. Field, line-item,
  observation, and raw-payload fingerprints therefore remain stable when
  equivalent provider evidence arrays are reordered.
- 2026-06-06: Candidate deduplication now uses deterministic evidence locator
  selection as well. Reordered but equivalent evidence arrays no longer cause
  duplicate line-item candidates to survive dedupe.
- 2026-06-06: Deterministic evidence-locator selection now lives in
  `lib/extraction/evidence_locator.py` and is shared by candidate fingerprints,
  candidate deduplication, and invoice aggregate line-item dedupe. Canonical
  invoice aggregates no longer depend on provider evidence-array order.
- 2026-06-06: Cross-run repeatability drift no longer compares
  `rejectionDistribution`. The fingerprint is still required and recomputed per
  report as rejected-noise telemetry through `candidateAdmissionSummary`, but
  deterministic repeatability drift is limited to document-family, selected
  region/task, admitted candidate, canonical output, and review-task identity.
- 2026-06-06: The shared OpenAI-compatible vision adapter now preserves the
  complete schema-validated direct model-output payload, including required
  `confidence`, when passing data to Granite/Qwen normalization. Confidence is
  still exposed separately as transport telemetry, but downstream contract
  validation and Claim/envelope construction no longer have to synthesize null
  confidence after the adapter strips a required field.
- 2026-06-06: The vision adapter no longer unwraps a schema-valid
  `{"normalized": ..., "confidence": ...}` wrapper into the inner
  `normalized` object. Adapter output is now the exact JSON object that passed
  the response schema; any legacy wrapper shape must be represented by an
  explicit schema or rejected before downstream normalization.
- 2026-06-06: Granite visual crop retry usefulness now prefers the normalized
  region envelope and typed Claims when available. A crop response with
  line-item-shaped JSON but no anchored Claims is treated as not useful and may
  retry full page instead of letting JSON shape heuristics decide acceptance.

- 2026-06-09: D8 quality outcomes are now persisted decisions in the database.
  Migration `087_phase8_5_quality_outcome.sql` adds
  `document_extractions.quality_outcome` with the outcome vocabulary CHECK, and
  `persist_extraction_run` stores the resolver outcome from the aggregate
  payload metadata; rows without a resolver outcome stay NULL.
- 2026-06-09: Document detail now exposes the D8 decision surface. Current
  document/aggregate extraction payloads include `qualityOutcome`, projected
  `claimResolutionDecisions` (decision + reason code per canonical key),
  `regionJobCoverage` when recorded, and contributing `sourceFamilies`;
  OpenAPI `ExtractionSummary` and the web types are aligned.
- 2026-06-09: The review `rerun_extraction` action no longer enqueues a
  document-level Granite `extract` job (which live routing rejects fail-closed
  by design). Reruns re-enter the pipeline at Smart Parse: a deduplicated
  `semantic_annotate` job carrying reviewer intent fields re-plans regions and
  fans out grounded Granite extraction before reconciliation.
- 2026-06-09: Extraction request intent (`requested_by`,
  `requested_by_user_id`, `user_intent_reason`) is persisted into
  `document_extractions.metadata_json` instead of being discarded after the
  job payload, preserving run provenance past job pruning.
- 2026-06-09: `observation_review` and `line_item_review` tasks are
  actionable. Review tasks expose their candidate-reference metadata,
  observation and line-item candidates have read endpoints with
  contract-shaped evidence, and accept/reject decisions are recorded as
  `accepted`/`rejected` candidate status with audit events and task clearing.
  Accept intentionally does not promote to canonical facts; no new canonical
  fact types were introduced.
- 2026-06-09: The web client now selects evidence locators deterministically
  (richer-anchor-first, mirroring `lib/extraction/evidence_locator.py`)
  instead of reading `evidence[0]`, and the Viewer renders the evidence ref's
  actual page, only draws highlights when a bbox exists, and normalizes
  against stored page dimensions.

- 2026-06-09: Line-item Claim grouping is sibling-aware: region-level anchors
  with null row_index no longer collapse distinct rows into one merged group;
  identical repeated rows survive as separate occurrences keyed by content
  fingerprint plus occurrence index.
- 2026-06-09: semantic_region_id was removed from Claim/anchor identity
  hashing, evidence selection ordering, candidate dedupe keys, and aggregate
  line-item dedupe per the anchor contract; it remains evidence lineage only.
- 2026-06-09: Money parsing handles accounting negatives and comma-decimal
  locales deterministically and no longer fabricates USD; typed date claims
  normalize to ISO via the shared date parser; claim confidence normalizes to
  the [0,1] contract (percent-style values scaled, out-of-range dropped).
- 2026-06-09: Arithmetic invariants use the money tolerance and skip gaps
  explainable by an unextracted optional component in the gap's direction;
  invoice aggregates no longer fabricate totals.total from amount_paid.
- 2026-06-09: Aggregate reconciliation triggers when every region job is
  terminal (the worker's own in-flight job counts as settled), also fires from
  the worker failure path, serializes per annotation/schema with an advisory
  lock, skips when the current aggregate already covers the same region rows,
  and records region_job_coverage plus plan-skip telemetry; missing coverage
  demotes the quality outcome and adds an explicit validation check. Receipts
  gained a first-class aggregate lane through the registry projector.
- 2026-06-09: Planner fanout budgets rescue must-extract/continuation
  line-item regions instead of silently dropping them; canonical aggregates
  and document-observation projections share the candidate-layer echo and
  signal gates.
- 2026-06-09: Page-only Granite evidence is upgraded with deterministic
  Docling anchors (element_id+bbox or page-text span located from verbatim
  source text) before Claim construction, restoring anchored Claims,
  candidates, and aggregates for KVP documents; unmatched refs stay page-only
  and excluded. Dot-less observation claim keys are accepted by the
  document-observation aggregate lane.
- 2026-06-09: GPU corpus run 20260610T021547Z validated the above end to end:
  aggregates with persisted quality outcomes for invoice/EOB/receipt/
  observation lanes, a partial aggregate with missing_region_jobs=1 for a
  dead-lettered region, KVP candidates restored, and zero non-model job
  failures.

- 2026-06-10: Family-specific semantic-intent normalization was removed per the
  generalization spec: the medical-EOB semantic-type rewrite, synthetic
  retail-order/receipt payment-summary and EOB decision-page regions, the
  family-gated model payment-summary drops, and the service-record and
  real-estate-title region replacement modules are gone. Planning
  normalization is structural-only (grounding repair, low-value filtering,
  dedupe; version v2); deterministic floor coverage remains in the Docling
  structural-target lane, and the semantic canary now scores the same
  post-planning manifest the live service hands to Granite fanout.

## Deferred Work

- Plan-stage stochasticity (Qwen routing variance) is bounded by greedy/low-temperature
  decoding, Docling-anchored region identity, and treating plan drift as a quality
  signal; a fully deterministic plan is out of scope.
- Remaining migration order (highest leverage first): (1) keep expanding the resolver
  registry while retiring any remaining non-Claim compatibility paths; (2) refactor
  schemas into fragments+registry.
