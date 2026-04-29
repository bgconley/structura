# Phase 8.5 Qwen3-VL-4B Smart Parse And Canary Hardening Spec

## Purpose

This spec defines the next Phase 8.5 realignment: replace the default Smart
Parse Qwen3-VL-2B semantic service with Qwen3-VL-4B, disable the active
Qwen3-VL-8B service path for now, and harden the Granite extraction layer so
real documents do not lose useful region-level output during normalization,
aggregation, or review routing.

The canonical Phase 8.5 pipeline remains:

```text
Docling physical parse
-> Qwen3-VL smart semantic annotation
-> Granite 4.0 3B Vision targeted structured extraction
-> validators / provenance / review policy
-> canonical facts + evidence/search layer
```

Docling remains the physical parse authority. Qwen remains the semantic
planner. Granite remains the structured extractor. Validators and review policy
remain the only promotion gate.

## Current Code Seams

The implementation must use the existing Phase 8.5 seams instead of adding a
parallel pipeline:

- `lib/model_runtime/profiles.py` owns profile identity, source engine, context
  limits, modality limits, and live-profile requirements.
- `compose.yaml` owns runtime placement for `model-qwen-semantic`,
  `model-qwen`, `model-granite`, `model-embed`, and `model-vl-embed`.
- `workers/model_services/start_qwen_vllm.sh` already supports model ID, dtype,
  max model length, max sequence count, KV cache dtype, and multimodal input
  limits through environment variables.
- `contracts/schemas/semantic_annotation_model_output.v1.schema.json` and
  `contracts/schemas/semantic_annotation_manifest.v1.schema.json` are the
  semantic annotation contracts. They must be preserved and expanded
  additively.
- `lib/semantic_annotations/qwen_gateway.py` owns Qwen semantic prompting,
  structured-output schema forwarding, and mode-to-profile selection.
- `lib/semantic_annotations/jobs.py` owns semantic job enqueue rules, user
  intent, rescue caps, and dedupe.
- `lib/extraction/gateways/_vision.py`, `lib/extraction/granite_prompting.py`,
  and `lib/extraction/model_output_schemas.py` own Granite routing, prompts, and
  model-output schema selection.
- `lib/extraction/model_output_normalization.py` owns model-output repair and
  mapping before canonical candidate persistence.
- `lib/extraction/reconciliation.py` and
  `lib/extraction/reconciliation_repository.py` own aggregate extraction
  construction from region outputs.
- `database/078_phase8_5_region_extraction_scope.sql` already introduced
  region-scoped extraction rows. This should be extended, not bypassed.

## Runtime Target

The active Smart Parse service is:

```text
service: model-qwen-semantic
port: 8104
profile: qwen3-vl-4b-semantic:v1
base model: Qwen/Qwen3-VL-4B-Instruct
source_engine: qwen3_vl_4b
dtype: bfloat16
max_model_len: 32768
max_num_seqs: 2
limit_mm_per_prompt: {"image": 4, "video": 0}
gpu: Blackwell GPU 0
```

The implementation may probe `kv_cache_dtype=fp8`, but it must fall back cleanly
if the installed vLLM/Qwen path rejects it. Smart Parse must use the same
Docling-grounded semantic manifest contract that the 2B path used. Smart Parse
now attempts four page images per request to match the historical 2B fan-in
shape. Exact Docling page coverage remains mandatory; if a multi-image response
omits a page annotation, the adapter retries that window as one-page requests
with whole-document Docling context and records fallback telemetry.

Granite remains on Blackwell GPU 1. Visual embedding may remain on GPU 1 only if
it continues to fit with Granite under live load. The 3090 is not required for
the 2B to 4B semantic swap.

## Qwen8 Disabled Semantics

Qwen3-VL-8B is disabled/deferred for this evaluation target. The implementation
must not silently remap High Quality Parse or rescue jobs to Qwen3-VL-4B.

Required behavior:

1. Default Smart Parse uses Qwen3-VL-4B through the existing smart semantic
   contract.
2. High Quality Parse endpoints, UI controls, corpus flags, and job enqueue
   paths remain contract-visible, but they return a clear disabled/deferred
   result while the 8B service is removed from the active runtime.
3. Allow 8B Rescue remains a preserved intent contract, but no automatic rescue
   job is enqueued while the 8B service is disabled.
4. Historical Qwen3-VL-2B and Qwen3-VL-8B provenance values remain readable.
   Do not delete enums, migrations, contract values, or stored metadata needed
   to interpret older runs.
5. `needs_human_review`, `insufficient_signal`, and `pipeline_failed` keep their
   Phase 8.5 meanings. The absence of Qwen8 must not convert document-quality
   uncertainty into worker failure.

## Semantic Contract Preservation

The existing Qwen semantic manifest remains the model-facing contract. The
contract should be expanded additively for broader document routing, not replaced
or made canonical fact JSON.

Add document-family values such as:

- `retail_order`
- `real_estate_title`
- `mortgage_escrow_statement`
- `financial_dispute_form`
- `travel_receipt`
- `restaurant_receipt`
- `generic_form`
- `unsupported_document`
- `no_extraction_target`

Add semantic-region values such as:

- `retail_order_line_item_table`
- `receipt_payment_summary`
- `seller_information_block`
- `escrow_summary`
- `mortgage_payment_summary`
- `dispute_transaction_table`
- `dispute_reason_block`
- `generic_form_kvp`
- `no_extraction_target`
- `unsupported_document_region`

Add target-schema values only where Structura has a downstream mapping or
observation path. Unsupported useful data should target a reviewable observation
schema, not an invented invoice/EOB/receipt schema.

The Qwen prompt must explicitly instruct the model to route unfamiliar forms to
generic observations or unsupported/no-target states instead of forcing them into
invoice, receipt, or medical EOB families.

## Granite Model-Output Contracts

Granite must continue to emit small model-output schemas that Structura maps into
canonical candidates or reviewable observations. Granite output must not become
canonical application JSON directly.

Existing model-output schemas remain:

- `granite_invoice_line_items.v1`
- `granite_payment_summary.v1`
- `granite_medical_service_lines.v1`

Add model-output schemas for the expanded routing set:

- `granite_receipt_line_items.v1`
- `granite_receipt_payment_summary.v1`
- `granite_retail_order.v1`
- `granite_real_estate_title_seller_info.v1`
- `granite_mortgage_escrow_statement.v1`
- `granite_dispute_form.v1`
- `granite_generic_kvp.v1`

Schemas should be bounded for vLLM structured-output reliability: shallow
objects, bounded arrays, `maxItems`, `maxLength`, explicit nullable fields where
needed, and no deep `$ref` or complex composition unless live capability probes
prove support.

## Granite Routing

Routing must be driven by semantic-region task and available Docling grounding,
not by a broad document guess alone.

Required routing behavior:

1. Table-like semantic types use Granite table extraction with `<tables_json>`,
   page/crop image input, and Docling table/row context when available.
2. Payment, billing, summary, seller-info, escrow, and dispute blocks use
   schema-based KVP extraction.
3. Unknown form regions use `granite_generic_kvp.v1` and become reviewable
   observations unless a canonical mapper explicitly supports them.
4. Low-signal, boilerplate, blank, or irrelevant regions become
   `insufficient_signal` or `no_extraction_target`; they must not be coerced
   into invoice/EOB/receipt output.
5. Sibling region successes remain usable even if another region times out or
   returns invalid output.

Structured output through vLLM `response_format: json_schema` should be used
when the gateway capability probe accepts it. Prompt-level schema instructions
and local validators remain mandatory because live vLLM structured-output
behavior can drift by backend, schema shape, and model path.

## Normalization Rules

Normalizers must be defensive around arbitrary model JSON:

1. Accept dict, list, string, null, schema echo, wrapped `data`/`normalized`
   payloads, and flat model fields without throwing `AttributeError` or
   `TypeError`.
2. Record repairs, rejected fields, wrapper unwrapping, schema echo rejection,
   unsupported field families, and evidence gaps in `normalization_json`.
3. Preserve useful raw fields as reviewable observations when canonical mapping
   is unavailable.
4. Mark repaired, partial, unsupported, or low-evidence output as
   `needs_human_review` unless validators prove it can be cleanly accepted.
5. Never let model output bypass canonical validators or review policy.

The app owns `document_id`, `created_at`, promotion state, user identity, review
state, provenance linkage, and canonical schemas. Models should not populate
those application-owned fields.

## Reviewable Observation Layer

Phase 8.5 needs a generic observation persistence path for useful data that does
not yet belong in canonical invoice, receipt, or EOB candidates.

The observation layer should store:

- document and extraction IDs
- semantic annotation and semantic region IDs
- semantic type and model-output schema
- observation family and field name
- scalar value or structured JSON value
- confidence and review status
- evidence refs and source page/region provenance
- normalization metadata

The observation layer is for title/seller-info, escrow, dispute, unsupported
form fields, and other useful extracted facts that are not yet canonical. It
should be queryable for review, evidence display, search projection, and future
canonical mappers without pretending every document is an invoice, receipt, or
medical EOB.

## Aggregation Rules

Aggregates are document-level read models built from current region outputs.
They must not erase richer region-level candidates.

Required aggregation behavior:

1. Build an invoice aggregate only when invoice identity evidence or invoice
   region schemas support it.
2. Build receipt/order aggregates only when receipt/order evidence supports
   them.
3. Do not create invoice or EOB aggregates for title, escrow, dispute, generic
   form, unsupported, or no-target documents.
4. Payment-summary regions may update totals/payment fields, but they cannot
   delete service or line-item candidates.
5. Later low-detail regions cannot supersede richer region output.
6. Aggregate evidence must preserve source extraction ID and semantic region ID.
7. Partial region failure should create review/diagnostic metadata while
   preserving successful sibling region outputs.

## Private Canary Gate

Create a private, non-committed Phase 8.5 canary manifest for the nine recent PDFs
plus the earlier BMW invoice and Anthem denial/EOB documents. Commit only a
schema/template for the manifest, not private file paths.

Each manifest entry should define:

- source document path
- expected document family
- allowed semantic target schemas
- required candidate or observation invariants
- allowed quality outcomes
- `must_not_happen` regressions

Initial canary expectations:

- BMW invoice: service line-item candidates survive payment-summary extraction.
- Anthem denial/EOB: medical service or denial fields route to medical/EOB
  candidates or reviewable medical observations.
- BH Photo order: retail order or receipt candidates/observations are produced;
  timeout preserves completed sibling regions.
- Phenix Title seller info: routes to real-estate/title observations, not
  invoice/EOB.
- UWM escrow statement: routes to mortgage/escrow observations, not medical EOB.
- Generic scans: may become `insufficient_signal` or `no_extraction_target`, but
  must not fabricate invoice/EOB output.
- Receipts: merchant, totals, payment, and line-item fields map into
  receipt/order candidates where evidence supports them.

The canary report must include Qwen8 call count, Qwen smart profile identity,
Granite profile identity, document family, semantic regions, extraction scopes,
candidate counts, observation counts, aggregate availability, failed runtime
jobs, review outcomes, and provenance checks.

## Non-Goals

1. Do not start Phase 9.
2. Do not delete Qwen2B or Qwen8 historical contracts/provenance support.
3. Do not fine-tune Qwen or Granite as part of this change.
4. Do not introduce ColQwen or reranking changes in this pass.
5. Do not force every document into a narrow canonical schema.
6. Do not make the private canary corpus public or commit private file paths.

## Acceptance Criteria

This realignment is complete only when:

1. Default Smart Parse launches Qwen3-VL-4B on `model-qwen-semantic:8104`.
2. Active runtime and private canary validation show zero Qwen8 calls.
3. High Quality Parse and Allow 8B Rescue remain explicit but disabled/deferred
   while Qwen8 is out of active runtime.
4. Existing semantic annotation contracts are preserved and expanded
   additively.
5. Granite region routing uses table/KVP/generic-observation paths instead of
   broad document guesses.
6. Normalization never crashes on arbitrary model JSON.
7. Useful unsupported data is persisted as reviewable observations.
8. Aggregates preserve richer sibling region outputs and do not masquerade
   unsupported docs as invoice/EOB.
9. The private canary gate passes with Qwen3-VL-4B Smart Parse only.

## Sources

- Qwen3-VL-4B model repository: <https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct>
- vLLM structured outputs: <https://docs.vllm.ai/en/latest/features/structured_outputs/>
- Granite 4.0 3B Vision model card: <https://huggingface.co/ibm-granite/granite-4.0-3b-vision>
- Docling document model: <https://docling-project.github.io/docling/concepts/docling_document/>
- Docling extraction examples: <https://docling-project.github.io/docling/examples/extraction/>
- Qwen structured-output guidance: <https://www.alibabacloud.com/help/en/model-studio/qwen-structured-output>
