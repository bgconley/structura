# Phase 8.5 Qwen Structured Output Design

## Purpose

This spec defines the Qwen3-VL semantic annotation output contract for Phase 8.5.
It exists because live Qwen semantic annotation failed on real documents by producing
useful but overlong JSON that was truncated and therefore invalid. The fix is not to
starve Qwen of semantic space. The fix is to make the output format enforceable,
validate it before persistence, and keep the prompt focused on semantic planning.

The semantic annotation layer remains:

```text
Docling physical parse
-> Qwen3-VL semantic annotation manifest
-> Granite targeted extraction
-> validators / provenance / review
-> canonical facts
```

Docling is the physical parse authority. Qwen is the semantic planner. Granite is
the structured extractor. Validators and human review remain the truth gate.

## Research Basis

- Alibaba Qwen structured-output guidance says to use `response_format` JSON mode,
  include the word `JSON` in prompts, disable thinking mode for structured output,
  validate downstream, retry or rewrite invalid output, and avoid low `max_tokens`
  because it can truncate JSON.
  Source: <https://www.alibabacloud.com/help/en/model-studio/qwen-structured-output>
- vLLM supports structured outputs through JSON Schema using OpenAI-compatible
  `response_format` and `structured_outputs` request parameters. Newer vLLM versions
  deprecate older `guided_json` fields in favor of `structured_outputs`.
  Source: <https://docs.vllm.ai/en/latest/features/structured_outputs/>
- Qwen3-VL maintainers point strict JSON users toward vLLM structured output
  backends such as xgrammar.
  Source: <https://github.com/QwenLM/Qwen3-VL/issues/1652>
- Alibaba Qwen OCR/KIE guidance uses the prompt pattern: given a schema, fill the
  schema, output valid JSON only, do not fabricate, use null when missing, mark
  unclear visual text, and provide no explanation.
  Source: <https://www.alibabacloud.com/help/en/model-studio/qwen-vl-ocr>
- Qwen3-VL docs emphasize document parsing, OCR/KIE, grounding, long-document
  understanding, and visual IDs for multiple inputs.
  Source: <https://github.com/QwenLM/Qwen3-VL>

## Goals

1. Make Qwen semantic manifests valid JSON by construction when the serving backend
   supports structured output.
2. Preserve Qwen's semantic usefulness by constraining shape and vocabulary rather
   than imposing tiny global region limits.
3. Prevent semantic annotations from becoming canonical facts or leaking invented
   field values into routing metadata.
4. Preserve Docling grounding and reject unknown or cross-page references before
   persistence.
5. Give Granite enough targeted context to extract structured fields without asking
   Qwen to extract those values.

## Non-Goals

1. Do not start Phase 9 answer synthesis.
2. Do not replace Docling with Qwen as parser.
3. Do not accept Qwen-produced provenance fields; Structura assigns model
   provenance from the invoked adapter/profile.
4. Do not auto-enable chart extraction tasks before Granite/analysis contracts own
   chart outputs.
5. Do not silently repair or persist partial malformed JSON.

## Response Envelope

Qwen must return one JSON object matching this logical envelope:

```json
{
  "schema_name": "semantic_annotation_manifest",
  "schema_version": "v1",
  "document_type": "medical_eob",
  "pages": [],
  "regions": [],
  "quality_flags": {},
  "confidence": {}
}
```

The model-runtime client may accept either the direct envelope above or the existing
compatibility wrapper:

```json
{
  "normalized": {
    "schema_name": "semantic_annotation_manifest",
    "schema_version": "v1",
    "document_type": "medical_eob",
    "pages": [],
    "regions": [],
    "quality_flags": {}
  },
  "confidence": {
    "overall": 0.86
  }
}
```

Internally, Structura normalizes both forms to the direct manifest envelope before
semantic policy validation.

## JSON Schema

The schema should be committed as
`contracts/schemas/semantic_annotation_manifest.v1.schema.json`.

The schema uses JSON Schema draft 2020-12, `additionalProperties: false` at every
object level, and required fields for stable downstream parsing. The model-facing
schema must stay within vLLM/xgrammar's supported structured-output subset; do not
use keywords such as `uniqueItems`, `oneOf`, `anyOf`, or `allOf`. Enforce those
deeper constraints in Structura's local schema/policy validators instead.

Top-level required fields:

```json
[
  "schema_name",
  "schema_version",
  "document_type",
  "pages",
  "regions",
  "quality_flags",
  "confidence"
]
```

Top-level properties:

```json
{
  "schema_name": { "const": "semantic_annotation_manifest" },
  "schema_version": { "const": "v1" },
  "document_type": {
    "type": "string",
    "enum": [
      "medical_eob",
      "insurance_denial",
      "medical_bill",
      "invoice",
      "receipt",
      "service_record",
      "legal",
      "tax",
      "financial",
      "other",
      "unknown"
    ]
  },
  "pages": { "type": "array" },
  "regions": { "type": "array" },
  "quality_flags": { "type": "object" },
  "confidence": { "type": "object" }
}
```

## Page Annotation Schema

`pages[]` must contain exactly one object per input page image. Runtime validation,
not JSON Schema alone, enforces exact page coverage against the request page IDs.

Required page fields:

```json
[
  "page_id",
  "page_number",
  "page_role",
  "document_type_hint",
  "extraction_usefulness",
  "is_boilerplate",
  "has_structured_targets",
  "ambiguous",
  "escalation_required",
  "escalation_reasons",
  "reason",
  "confidence"
]
```

Allowed `page_role` values:

```text
document_header
claim_summary
payment_summary
line_items
denial_or_decision
instructions
contact_or_identity
terms_or_boilerplate
signature_or_authorization
image_or_figure
mixed
unknown
```

Allowed `extraction_usefulness` values:

```text
none
low
medium
high
unknown
```

Allowed `escalation_reasons` values:

```text
poor_ocr
ambiguous_document_type
missing_docling_grounding
high_risk_domain
low_confidence
validation_sensitive
unsupported_schema
visual_degradation
```

`reason` is nullable string with max length 240. `confidence` is nullable number in
`[0, 1]`.

## Region Annotation Schema

`regions[]` contains Granite routing targets, not extracted values. It may be empty
for pages with no useful structured targets.

Required region fields:

```json
[
  "semantic_type",
  "priority",
  "granite_task",
  "target_schema",
  "expected_fields",
  "grounding",
  "review_required",
  "reason",
  "confidence"
]
```

Allowed `semantic_type` values:

```text
document_header
billing_summary
payment_summary
patient_responsibility_summary
denial_or_coverage_decision
appeal_or_next_steps
covered_services_line_item_table
invoice_line_item_table
receipt_line_item_table
service_record_line_item_table
service_summary
vehicle_or_asset_block
diagnostic_summary
policy_or_plan_identifiers
contact_block
signature_block
chart
figure
legal_clause
tax_summary
boilerplate
unmatched_region
unknown
```

Allowed `priority` values:

```text
low
medium
high
critical
```

Allowed `granite_task` values:

```text
kvp
tables_json
tables_html
tables_otsl
ignore
```

Chart tasks are deliberately excluded from auto-routing in this schema revision.
Qwen may mark chart-like content as `semantic_type: "chart"` with
`granite_task: "ignore"` and `review_required: true`. Phase 9 may add explicit chart
contracts later.

Allowed `target_schema` values:

```text
receipt
invoice
medical_eob
null
```

`expected_fields` contains field names only, never observed values. It allows 0 to
20 items. Each item is a lower snake-case or dotted field path string with max
length 96.

The `grounding` object has:

```json
{
  "kind": "page",
  "page_id": "uuid-or-null",
  "element_id": "uuid-or-null",
  "table_id": "uuid-or-null"
}
```

Allowed `grounding.kind` values:

```text
page
element
table
unmatched_region
```

Grounding rules are enforced by runtime validation because the schema cannot know
which Docling IDs were present in the request.

## Critical User Message

The Qwen user message must be concise and stable. It should not contain tiny global
region caps. It should include the word `JSON` because JSON mode requires it.

Base prompt:

```text
You are Structura's semantic annotation planner. Return valid JSON only, matching the provided JSON Schema. Do not use markdown fences or explanatory text.

Docling is the physical parse authority. Use the provided Docling page_id, element_id, and table_id values whenever possible. Prefer table_id for tables, element_id for text clusters, and page_id only when no smaller Docling object fits.

Your job is semantic planning, not extraction. Do not transcribe names, addresses, dates, dollar amounts, diagnosis text, policy numbers, VINs, or other canonical values. expected_fields must contain field names only, never observed values.

Identify the structured regions that Granite should extract. Include all high-value regions on the provided page images, but do not list decorative, duplicate, or boilerplate regions. If a page has no useful extraction target, return its page annotation and no region for that page.

Use target_schema medical_eob for EOBs, insurance denials, claim/payment responsibility documents, and medical billing summaries. Use invoice for bills/invoices. Use receipt for receipts, service records, and itemized purchase/service documents. Use null when no supported schema applies.

If you see a useful target but cannot ground it to Docling, use grounding.kind unmatched_region, semantic_type unmatched_region, confidence below 0.5, and review_required true.

If the document is ambiguous, visually degraded, high risk, or needs Qwen8B review, set escalation_required true and include escalation_reasons.
```

Smart mode suffix:

```text
Smart mode: prioritize high and medium priority targets. Keep low-priority targets only when omitting them would likely affect extraction correctness.
```

High-quality/rescue suffix:

```text
High Quality mode: be more exhaustive. Include low-priority targets when they may affect legal, medical, financial, tax, insurance, or service-record interpretation.
```

The prompt then appends compact Docling context as JSON. The context must include
page IDs, image hashes, element IDs, table IDs, page numbers, bounded snippets,
and quality flags. It must not include full raw document text.

## vLLM Request Strategy

The client should try structured output in this order:

1. OpenAI-compatible JSON Schema:

```json
{
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "semantic_annotation_manifest",
      "schema": {}
    }
  }
}
```

2. vLLM structured outputs request parameter.

When using the OpenAI Python SDK this is passed as `extra_body`, but Structura's
model runtime posts raw JSON over HTTP. For the raw request body, send
`structured_outputs` as a top-level vLLM parameter:

```json
{
  "structured_outputs": {
    "json": {}
  }
}
```

3. Compatibility fallback:

```json
{
  "response_format": {
    "type": "json_object"
  }
}
```

The schema object is the same in all structured-output paths.

The request must use non-thinking mode. Temperature remains `0.0`. Do not use a
small output-token limit as the format-control mechanism. A safe default for semantic
annotation is 4096 output tokens for one-page smart chunks and 8192 output tokens
for high-quality multi-page chunks when the service supports it. If the backend only
supports a lower maximum, the gateway should reduce page chunk size before reducing
semantic richness.

## Validation Pipeline

Validation happens before persistence and before Granite job enqueue.

Transport validation:

1. Response contains non-empty assistant content.
2. `finish_reason` is not `length`.
3. Content parses as a JSON object after optional direct-envelope normalization.
4. Content validates against `semantic_annotation_manifest.v1.schema.json`.

Semantic validation:

1. `pages[]` covers exactly the input page IDs in the request chunk.
2. `pages[].page_number` matches the Docling page number for that `page_id`.
3. No duplicate page annotations.
4. Region semantic types, priorities, Granite tasks, and target schemas are allowed.
5. `page` grounding requires only `page_id`.
6. `element` grounding requires `page_id + element_id`, and the element belongs to
   that page.
7. `table` grounding requires `page_id + table_id`, and the table belongs to that
   page.
8. `unmatched_region` grounding requires no IDs, `semantic_type=unmatched_region`,
   `review_required=true`, and no auto Granite job.
9. `granite_task=ignore` never queues extraction.
10. `granite_task != ignore` requires `target_schema` in `receipt`, `invoice`,
    or `medical_eob`.
11. `tables_*` tasks should use table grounding when Docling provided a candidate
    table. Page grounding for a table task is allowed only with `review_required=true`.
12. Duplicate regions with the same grounding, semantic type, and task are rejected.
13. Unexpected value-bearing keys such as `value`, `amount`, `date`, `name`,
    `address`, `raw_text`, or `source_engine` outside approved schema positions are
    rejected by `additionalProperties: false`.

Policy validation:

1. Medical, insurance, legal, tax, and financial documents with low confidence or
   ambiguity trigger review/HQ policy.
2. Any unmatched region triggers review.
3. Any unsupported target schema triggers retry or failure, not best-effort routing.
4. Provenance is assigned from the actual model profile, never from Qwen output.

## Retry And Failure Behavior

The gateway retries at most once per request chunk for:

1. Invalid JSON.
2. JSON Schema validation failure caused by shape, not unsafe content.
3. `finish_reason=length`.
4. Missing page coverage.

Retry behavior:

1. If the failed request had multiple pages, split to one-page chunks and retry.
2. If the failed request already had one page, retry once with the same schema and
   a concise repair instruction that says: "Return only a complete JSON object
   matching the schema. Do not omit required fields."
3. Do not persist partial manifests from failed chunks.
4. Do not run a permissive JSON repair library for ambiguous truncated content.
5. Store failure status and raw diagnostic metadata only through the job failure path,
   not in current manifest tables.

## Granite Routing Rules

Qwen regions are only routing metadata.

Granite jobs are queued only when:

1. `granite_task` is not `ignore`.
2. Grounding is not `unmatched_region`.
3. `target_schema` is one of `receipt`, `invoice`, `medical_eob`.
4. The region passes semantic validation.

Granite receives:

1. Document ID.
2. Semantic annotation ID.
3. Semantic region ID.
4. Target schema and version.
5. Granite task.
6. Expected field names.
7. Docling grounding IDs.
8. Page/crop image bytes resolved from Docling assets.

Granite does not receive Qwen-generated canonical values because Qwen should not
generate them.

## Test Requirements

Unit tests:

1. Qwen client sends JSON Schema structured output when schema is provided.
2. Qwen client can fall back to `structured_outputs.json` or `json_object`.
3. Prompt contains the critical planning instructions and does not contain the old
   "at most two regions total" cap.
4. Invalid JSON retries once and then fails deterministically.
5. `finish_reason=length` is treated as retryable failure.
6. Schema validation rejects missing fields and extra value-bearing fields.
7. Semantic validation rejects unknown Docling IDs, cross-page IDs, duplicate regions,
   bad unmatched regions, unsupported target schemas, and unsafe table grounding.

Integration tests:

1. Manifest persistence remains atomic with targeted Granite job enqueue.
2. Invalid semantic output leaves no current manifest and no extraction jobs.
3. MRI/insurance denial fixture maps to `medical_eob` or `insurance_denial` document
   type and targets `medical_eob` extraction schema.
4. BMW service record fixture maps to `service_record` document type and targets
   `receipt` or `invoice` extraction schema only for structured service/billing
   regions.

Live GPU smoke:

1. Qwen2B smart semantic annotation returns valid schema JSON for the MRI PDF.
2. Qwen8B HQ semantic annotation returns valid schema JSON for the MRI PDF.
3. Qwen2B smart semantic annotation returns valid schema JSON for the BMW PDF.
4. Qwen8B HQ semantic annotation returns valid schema JSON for the BMW PDF.
5. Granite targeted jobs are enqueued from validated regions only.

## Acceptance Criteria

1. The provisional `qwen_gateway.py` prompt edit that lowered output tokens and
   limited output to two regions is removed or replaced.
2. Structured-output schema is committed and used by live Qwen requests.
3. Qwen prompt is schema-focused and allows useful semantic coverage.
4. Invalid, truncated, or unsafe model responses do not persist current manifests.
5. Tests prove that Qwen output is routing metadata only.
6. The private MRI/BMW corpus run can complete Qwen semantic annotation without JSON
   truncation failures before Granite extraction proceeds.
