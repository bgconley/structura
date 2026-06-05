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
| `source_engine` | enum | `docling \| qwen \| granite` - truthful provenance only |
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
- 2026-06-05: Invoice semantic-region reconciliation now prefers persisted
  `RegionExtractionEnvelope` facts and line items when present, with the legacy raw
  payload path retained only for rows that predate the envelope. This is a compatibility
  bridge toward D3/D6, not the final `Claim` IR or generic resolver.
- 2026-06-05: The first `Claim` IR module is implemented in `lib/extraction/claims.py`.
  It emits deterministic claim IDs from `(document_id, anchor, canonical_key,
  typed_value)`, drops unanchored values, normalizes Granite provenance to `granite`,
  and converts region-envelope facts and line items into anchored typed claims.
- 2026-06-05: Invoice semantic-region reconciliation now prefers explicit Claims over
  both region envelopes and raw normalized payloads. The older envelope/raw paths remain
  only as compatibility fallbacks while the generic resolver and registry migration are
  still in progress.
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
- 2026-06-05: Invoice semantic-region aggregation no longer uses raw
  `normalized_json` payloads or envelope-only reconciliation by default. Runtime
  aggregation requires Claims; raw invoice dicts and pre-Claim typed envelopes remain
  available only through explicit legacy compatibility flags for pre-envelope and
  pre-Claim unit coverage.
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

## Deferred Work

- Plan-stage stochasticity (Qwen routing variance) is bounded by greedy/low-temperature
  decoding, Docling-anchored region identity, and treating plan drift as a quality
  signal; a fully deterministic plan is out of scope.
- Remaining migration order (highest leverage first): (1) expand the resolver registry
  beyond invoice, receipt, and medical EOB while retiring raw-payload compatibility
  paths; (2) refactor schemas into fragments+registry.
