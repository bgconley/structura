# Phase 8.5 Qwen Structured Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Phase 8.5 Qwen semantic annotation produce schema-valid, Docling-grounded JSON without over-constraining semantic coverage.

**Architecture:** Add a formal semantic annotation JSON Schema, send it through vLLM structured-output request fields, keep Qwen's user prompt focused on semantic planning, and validate response shape plus Docling grounding before persistence or Granite job enqueue. Qwen remains a planner; Granite remains the extractor; Docling remains physical truth.

**Tech Stack:** Python 3.11, FastAPI service modules, existing `lib/model_runtime` OpenAI-compatible clients, JSON Schema draft 2020-12, vLLM OpenAI-compatible structured outputs, PostgreSQL-backed semantic annotation persistence, pytest.

---

## Scope

This plan hardens the Qwen semantic annotation generation contract. It does not start Phase 9, does not change Granite extraction schemas, and does not promote Qwen output to canonical facts.

## File Structure

- Create `contracts/schemas/semantic_annotation_manifest.v1.schema.json`: strict Qwen semantic output schema.
- Modify `lib/model_runtime/contracts.py`: add optional structured output schema fields to `VisionGenerateRequest`.
- Modify `lib/model_runtime/clients/_openai_vision.py`: send JSON Schema structured-output payloads and detect truncation.
- Modify `lib/semantic_annotations/qwen_gateway.py`: replace provisional tight prompt and pass the semantic schema.
- Modify `lib/semantic_annotations/policy.py`: add schema-aligned enums and grounding/value safety validation.
- Create `lib/semantic_annotations/schema.py`: load and expose the semantic annotation JSON Schema for model requests and validators.
- Modify `tests/unit/model_runtime/test_qwen_client.py`: assert structured-output payload shape and truncation handling.
- Modify `tests/unit/semantic_annotations/test_gateways.py`: assert prompt contract and retry/failure behavior.
- Modify `tests/unit/semantic_annotations/test_policy.py`: assert grounding and unsafe-value validation.
- Modify `tests/integration/test_phase8_5_semantic_annotations.py`: assert invalid semantic output persists nothing and queues no Granite jobs.

## Task 1: Add The Semantic Manifest JSON Schema

**Files:**
- Create: `contracts/schemas/semantic_annotation_manifest.v1.schema.json`
- Create: `lib/semantic_annotations/schema.py`
- Test: `tests/unit/semantic_annotations/test_policy.py`

- [ ] **Step 1: Write the failing schema-load test**

Add this test to `tests/unit/semantic_annotations/test_policy.py`:

```python
def test_semantic_annotation_schema_accepts_minimal_valid_manifest() -> None:
    from jsonschema import Draft202012Validator

    from lib.semantic_annotations.schema import semantic_annotation_manifest_schema

    schema = semantic_annotation_manifest_schema()
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(
        {
            "schema_name": "semantic_annotation_manifest",
            "schema_version": "v1",
            "document_type": "medical_eob",
            "pages": [
                {
                    "page_id": "11111111-1111-4111-8111-111111111111",
                    "page_number": 1,
                    "page_role": "claim_summary",
                    "document_type_hint": "medical_eob",
                    "extraction_usefulness": "high",
                    "is_boilerplate": False,
                    "has_structured_targets": True,
                    "ambiguous": False,
                    "escalation_required": False,
                    "escalation_reasons": [],
                    "reason": "Claim summary and responsibility fields are visible.",
                    "confidence": 0.91,
                }
            ],
            "regions": [
                {
                    "semantic_type": "patient_responsibility_summary",
                    "priority": "high",
                    "granite_task": "kvp",
                    "target_schema": "medical_eob",
                    "expected_fields": ["patient_responsibility", "plan_paid"],
                    "grounding": {
                        "kind": "page",
                        "page_id": "11111111-1111-4111-8111-111111111111",
                        "element_id": None,
                        "table_id": None,
                    },
                    "review_required": False,
                    "reason": "Summary block is a high-value extraction target.",
                    "confidence": 0.87,
                }
            ],
            "quality_flags": {
                "needs_high_quality_pass": False,
                "visual_degradation": False,
            },
            "confidence": {"overall": 0.89},
        }
    )
```

Run: `python -m pytest -q tests/unit/semantic_annotations/test_policy.py::test_semantic_annotation_schema_accepts_minimal_valid_manifest`

Expected: FAIL with `ModuleNotFoundError` for `lib.semantic_annotations.schema`.

- [ ] **Step 2: Add `lib/semantic_annotations/schema.py`**

Create the module:

```python
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "contracts"
    / "schemas"
    / "semantic_annotation_manifest.v1.schema.json"
)


@lru_cache(maxsize=1)
def semantic_annotation_manifest_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
```

- [ ] **Step 3: Add `contracts/schemas/semantic_annotation_manifest.v1.schema.json`**

Create a draft 2020-12 schema with:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://structura.local/contracts/schemas/semantic_annotation_manifest.v1.schema.json",
  "title": "Semantic Annotation Manifest v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_name",
    "schema_version",
    "document_type",
    "pages",
    "regions",
    "quality_flags",
    "confidence"
  ],
  "properties": {
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
    "pages": {
      "type": "array",
      "maxItems": 8,
      "items": { "$ref": "#/$defs/pageAnnotation" }
    },
    "regions": {
      "type": "array",
      "maxItems": 32,
      "items": { "$ref": "#/$defs/regionAnnotation" }
    },
    "quality_flags": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "needs_high_quality_pass": { "type": "boolean" },
        "visual_degradation": { "type": "boolean" },
        "poor_ocr": { "type": "boolean" },
        "ambiguous_document_type": { "type": "boolean" },
        "reason": { "type": ["string", "null"], "maxLength": 240 }
      }
    },
    "confidence": { "$ref": "#/$defs/confidenceObject" }
  },
  "$defs": {
    "uuid": {
      "type": "string",
      "format": "uuid"
    },
    "confidence": {
      "type": ["number", "null"],
      "minimum": 0,
      "maximum": 1
    },
    "confidenceObject": {
      "type": "object",
      "additionalProperties": {
        "type": ["number", "string", "boolean", "array", "object", "null"]
      },
      "properties": {
        "overall": { "$ref": "#/$defs/confidence" }
      }
    },
    "pageAnnotation": {
      "type": "object",
      "additionalProperties": false,
      "required": [
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
      ],
      "properties": {
        "page_id": { "$ref": "#/$defs/uuid" },
        "page_number": { "type": "integer", "minimum": 1 },
        "page_role": {
          "type": "string",
          "enum": [
            "document_header",
            "claim_summary",
            "payment_summary",
            "line_items",
            "denial_or_decision",
            "instructions",
            "contact_or_identity",
            "terms_or_boilerplate",
            "signature_or_authorization",
            "image_or_figure",
            "mixed",
            "unknown"
          ]
        },
        "document_type_hint": {
          "type": ["string", "null"],
          "maxLength": 80
        },
        "extraction_usefulness": {
          "type": "string",
          "enum": ["none", "low", "medium", "high", "unknown"]
        },
        "is_boilerplate": { "type": "boolean" },
        "has_structured_targets": { "type": "boolean" },
        "ambiguous": { "type": "boolean" },
        "escalation_required": { "type": "boolean" },
        "escalation_reasons": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "type": "string",
            "enum": [
              "poor_ocr",
              "ambiguous_document_type",
              "missing_docling_grounding",
              "high_risk_domain",
              "low_confidence",
              "validation_sensitive",
              "unsupported_schema",
              "visual_degradation"
            ]
          }
        },
        "reason": { "type": ["string", "null"], "maxLength": 240 },
        "confidence": { "$ref": "#/$defs/confidence" }
      }
    },
    "regionAnnotation": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "semantic_type",
        "priority",
        "granite_task",
        "target_schema",
        "expected_fields",
        "grounding",
        "review_required",
        "reason",
        "confidence"
      ],
      "properties": {
        "semantic_type": {
          "type": "string",
          "enum": [
            "document_header",
            "billing_summary",
            "payment_summary",
            "patient_responsibility_summary",
            "denial_or_coverage_decision",
            "appeal_or_next_steps",
            "covered_services_line_item_table",
            "invoice_line_item_table",
            "receipt_line_item_table",
            "service_record_line_item_table",
            "service_summary",
            "vehicle_or_asset_block",
            "diagnostic_summary",
            "policy_or_plan_identifiers",
            "contact_block",
            "signature_block",
            "chart",
            "figure",
            "legal_clause",
            "tax_summary",
            "boilerplate",
            "unmatched_region",
            "unknown"
          ]
        },
        "priority": {
          "type": "string",
          "enum": ["low", "medium", "high", "critical"]
        },
        "granite_task": {
          "type": "string",
          "enum": ["kvp", "tables_json", "tables_html", "tables_otsl", "ignore"]
        },
        "target_schema": {
          "type": ["string", "null"],
          "enum": ["receipt", "invoice", "medical_eob", null]
        },
        "expected_fields": {
          "type": "array",
          "maxItems": 20,
          "items": {
            "type": "string",
            "pattern": "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*$",
            "maxLength": 96
          }
        },
        "grounding": { "$ref": "#/$defs/grounding" },
        "review_required": { "type": "boolean" },
        "reason": { "type": ["string", "null"], "maxLength": 240 },
        "confidence": { "$ref": "#/$defs/confidence" }
      }
    },
    "grounding": {
      "type": "object",
      "additionalProperties": false,
      "required": ["kind", "page_id", "element_id", "table_id"],
      "properties": {
        "kind": {
          "type": "string",
          "enum": ["page", "element", "table", "unmatched_region"]
        },
        "page_id": { "type": ["string", "null"], "format": "uuid" },
        "element_id": { "type": ["string", "null"], "format": "uuid" },
        "table_id": { "type": ["string", "null"], "format": "uuid" }
      }
    }
  }
}
```

- [ ] **Step 4: Run the test**

Run: `python -m pytest -q tests/unit/semantic_annotations/test_policy.py::test_semantic_annotation_schema_accepts_minimal_valid_manifest`

Expected: PASS.

## Task 2: Add Structured Output Support To Vision Requests

**Files:**
- Modify: `lib/model_runtime/contracts.py`
- Modify: `lib/model_runtime/clients/_openai_vision.py`
- Test: `tests/unit/model_runtime/test_qwen_client.py`

- [ ] **Step 1: Write failing request payload test**

Add this test to `tests/unit/model_runtime/test_qwen_client.py`:

```python
def test_qwen_client_sends_json_schema_structured_output_when_schema_is_present() -> None:
    seen: dict[str, object] = {}
    image_sha256 = hashlib.sha256(b"image-bytes").hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "Qwen/Qwen3-VL-2B-Instruct",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "schema_name": "semantic_annotation_manifest",
                                    "schema_version": "v1",
                                    "document_type": "invoice",
                                    "pages": [],
                                    "regions": [],
                                    "quality_flags": {},
                                    "confidence": {"overall": 0.9},
                                }
                            )
                        },
                    }
                ],
            },
        )

    client = QwenVLClient(
        profile=get_model_profile(QWEN_SEMANTIC_PROFILE),
        http_client_base_url="http://model-qwen-semantic:8104",
        transport=httpx.MockTransport(handler),
    )
    client.generate(
        VisionGenerateRequest(
            profile_name=QWEN_SEMANTIC_PROFILE,
            prompt_version="phase8_5-semantic-smart-v2",
            prompt="Return JSON only.",
            image_inputs=(
                ModelImageInput(
                    content=b"image-bytes",
                    mime_type="image/png",
                    sha256=image_sha256,
                ),
            ),
            response_schema_name="semantic_annotation_manifest",
            response_json_schema={"type": "object", "properties": {"schema_name": {"const": "semantic_annotation_manifest"}}},
            max_output_tokens=4096,
            temperature=0.0,
            timeout_seconds=30,
        )
    )

    payload = seen["payload"]
    assert isinstance(payload, dict)
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["name"] == "semantic_annotation_manifest"
    assert payload["response_format"]["json_schema"]["schema"]["type"] == "object"
    assert payload["structured_outputs"]["json"]["type"] == "object"
```

Run: `python -m pytest -q tests/unit/model_runtime/test_qwen_client.py::test_qwen_client_sends_json_schema_structured_output_when_schema_is_present`

Expected: FAIL because `response_json_schema` does not exist.

- [ ] **Step 2: Extend `VisionGenerateRequest`**

Modify `lib/model_runtime/contracts.py`:

```python
@dataclass(frozen=True)
class VisionGenerateRequest:
    profile_name: str
    prompt_version: str
    prompt: str
    image_inputs: tuple[ModelImageInput, ...]
    response_schema_name: str | None
    max_output_tokens: int
    temperature: float
    timeout_seconds: int
    response_json_schema: dict[str, object] | None = None
```

- [ ] **Step 3: Update `_openai_payload`**

In `lib/model_runtime/clients/_openai_vision.py`, replace the hard-coded
`"response_format": {"type": "json_object"}` with raw HTTP payload support for
OpenAI-compatible `response_format` and vLLM's top-level `structured_outputs`
request parameter. The OpenAI Python SDK calls this `extra_body`, but Structura
does not use the SDK for model-runtime calls.

```python
response_format: dict[str, object]
structured_outputs: dict[str, object] | None = None
if request.response_json_schema:
    schema_name = request.response_schema_name or "structured_response"
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "schema": request.response_json_schema,
        },
    }
    structured_outputs = {"json": request.response_json_schema}
else:
    response_format = {"type": "json_object"}
payload = {
    "model": profile.base_model,
    "messages": [{"role": "user", "content": content}],
    "max_tokens": request.max_output_tokens,
    "temperature": request.temperature,
    "response_format": response_format,
    "metadata": {
        "profile_name": request.profile_name,
        "prompt_version": request.prompt_version,
        "response_schema_name": request.response_schema_name,
    },
}
if structured_outputs is not None:
    payload["structured_outputs"] = structured_outputs
return payload
```

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest -q tests/unit/model_runtime/test_qwen_client.py`

Expected: PASS.

## Task 3: Treat Truncated Model Output As Retryable Protocol Failure

**Files:**
- Modify: `lib/model_runtime/clients/_openai_vision.py`
- Test: `tests/unit/model_runtime/test_qwen_client.py`

- [ ] **Step 1: Write failing truncation test**

Add this test:

```python
def test_qwen_client_rejects_length_truncated_structured_output() -> None:
    client = QwenVLClient(
        profile=get_model_profile(QWEN_VL_PROFILE),
        http_client_base_url="http://model-qwen:8100",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "model": "Qwen/Qwen3-VL-8B-Instruct",
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {"content": "{\"schema_name\":\"semantic"},
                        }
                    ],
                },
            )
        ),
    )

    with pytest.raises(ModelProtocolError, match="truncated"):
        client.generate(_request())
```

Run: `python -m pytest -q tests/unit/model_runtime/test_qwen_client.py::test_qwen_client_rejects_length_truncated_structured_output`

Expected: FAIL because `finish_reason` is ignored.

- [ ] **Step 2: Validate `finish_reason`**

In `_raw_message_content`, read `first.get("finish_reason")`. If it equals
`"length"`, raise:

```python
raise ModelProtocolError("Vision model response was truncated before valid JSON completed.")
```

- [ ] **Step 3: Run focused tests**

Run: `python -m pytest -q tests/unit/model_runtime/test_qwen_client.py`

Expected: PASS.

## Task 4: Replace The Qwen Prompt Contract

**Files:**
- Modify: `lib/semantic_annotations/qwen_gateway.py`
- Test: `tests/unit/semantic_annotations/test_gateways.py`

- [ ] **Step 1: Write failing prompt test**

Add this test:

```python
def test_qwen_semantic_prompt_is_schema_focused_without_region_starvation() -> None:
    source = _source_with_page_image()
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_2b",
        normalized_json=_semantic_payload(source.pages[0].page_id),
    )

    QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    assert client.request is not None
    prompt = client.request.prompt
    assert "Return valid JSON only" in prompt
    assert "Docling is the physical parse authority" in prompt
    assert "semantic planning, not extraction" in prompt
    assert "expected_fields must contain field names only" in prompt
    assert "at most two regions total" not in prompt
    assert "max_output_tokens" not in prompt
```

Run: `python -m pytest -q tests/unit/semantic_annotations/test_gateways.py::test_qwen_semantic_prompt_is_schema_focused_without_region_starvation`

Expected: FAIL until the prompt is replaced.

- [ ] **Step 2: Replace `_prompt` content**

Update `_prompt` to accept `quality_mode` and return this base text before the
Docling context:

```python
base_prompt = (
    "You are Structura's semantic annotation planner. Return valid JSON only, "
    "matching the provided JSON Schema. Do not use markdown fences or explanatory text.\n\n"
    "Docling is the physical parse authority. Use the provided Docling page_id, "
    "element_id, and table_id values whenever possible. Prefer table_id for tables, "
    "element_id for text clusters, and page_id only when no smaller Docling object fits.\n\n"
    "Your job is semantic planning, not extraction. Do not transcribe names, "
    "addresses, dates, dollar amounts, diagnosis text, policy numbers, VINs, or "
    "other canonical values. expected_fields must contain field names only, never "
    "observed values.\n\n"
    "Identify the structured regions that Granite should extract. Include all "
    "high-value regions on the provided page images, but do not list decorative, "
    "duplicate, or boilerplate regions. If a page has no useful extraction target, "
    "return its page annotation and no region for that page.\n\n"
    "Use target_schema medical_eob for EOBs, insurance denials, claim/payment "
    "responsibility documents, and medical billing summaries. Use invoice for "
    "bills/invoices. Use receipt for receipts, service records, and itemized "
    "purchase/service documents. Use null when no supported schema applies.\n\n"
    "If you see a useful target but cannot ground it to Docling, use grounding.kind "
    "unmatched_region, semantic_type unmatched_region, confidence below 0.5, and "
    "review_required true.\n\n"
    "If the document is ambiguous, visually degraded, high risk, or needs Qwen8B "
    "review, set escalation_required true and include escalation_reasons."
)
mode_suffix = (
    "High Quality mode: be more exhaustive. Include low-priority targets when they "
    "may affect legal, medical, financial, tax, insurance, or service-record interpretation."
    if quality_mode in {"high_quality", "rescue"}
    else "Smart mode: prioritize high and medium priority targets. Keep low-priority "
    "targets only when omitting them would likely affect extraction correctness."
)
return f"{base_prompt}\n\n{mode_suffix}\n\nDocling context JSON: {json.dumps(context, sort_keys=True)}"
```

- [ ] **Step 3: Pass the JSON Schema to Qwen**

In `_generate_for_source`, pass:

```python
from lib.semantic_annotations.schema import semantic_annotation_manifest_schema

VisionGenerateRequest(
    profile_name=profile_name,
    prompt_version=prompt_version,
    prompt=_prompt(source, quality_mode=quality_mode),
    image_inputs=_image_inputs(source, storage=self.storage),
    response_schema_name="semantic_annotation_manifest",
    response_json_schema=semantic_annotation_manifest_schema(),
    max_output_tokens=4096,
    temperature=0.0,
    timeout_seconds=60,
)
```

Do not use `1536` for semantic annotation output control.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest -q tests/unit/semantic_annotations/test_gateways.py`

Expected: PASS.

## Task 5: Normalize And Schema-Validate Qwen Output Before Dataclass Conversion

**Files:**
- Modify: `lib/semantic_annotations/qwen_gateway.py`
- Test: `tests/unit/semantic_annotations/test_gateways.py`

- [ ] **Step 1: Write failing extra-field rejection test**

Add this test:

```python
def test_live_qwen_gateway_rejects_value_bearing_extra_fields() -> None:
    source = _source_with_page_image()
    payload = _semantic_payload(source.pages[0].page_id)
    regions = payload["regions"]
    assert isinstance(regions, list)
    region = regions[0]
    assert isinstance(region, dict)
    region["value"] = "$42.00"
    client = FakeSemanticVisionClient(
        profile_name=QWEN_SEMANTIC_PROFILE,
        source_engine="qwen3_vl_2b",
        normalized_json=payload,
    )

    with pytest.raises(ModelProtocolError, match="schema"):
        QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")
```

Run: `python -m pytest -q tests/unit/semantic_annotations/test_gateways.py::test_live_qwen_gateway_rejects_value_bearing_extra_fields`

Expected: FAIL because current gateway does not JSON Schema validate normalized output.

- [ ] **Step 2: Add schema validation helper**

In `qwen_gateway.py`, add:

```python
from jsonschema import ValidationError, validate

from lib.semantic_annotations.schema import semantic_annotation_manifest_schema


def _validate_response_schema(normalized: dict[str, object]) -> None:
    try:
        validate(instance=normalized, schema=semantic_annotation_manifest_schema())
    except ValidationError as exc:
        raise ModelProtocolError(f"Invalid semantic annotation schema: {exc.message}") from exc
```

Call this before `_page_from_json` and `_region_from_json`.

- [ ] **Step 3: Update test fixture payloads**

Update `_semantic_payload` in `tests/unit/semantic_annotations/test_gateways.py`
to include new required fields:

```python
"schema_name": "semantic_annotation_manifest",
"schema_version": "v1",
"quality_flags": {"needs_high_quality_pass": False, "visual_degradation": False},
"confidence": {"overall": 0.89},
```

Add page fields `is_boilerplate`, `ambiguous`, `escalation_required`,
`escalation_reasons`, and `reason`. Add `element_id` and `table_id` nulls to
page-grounding objects.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest -q tests/unit/semantic_annotations/test_gateways.py`

Expected: PASS.

## Task 6: Harden Semantic Policy Grounding

**Files:**
- Modify: `lib/semantic_annotations/policy.py`
- Test: `tests/unit/semantic_annotations/test_policy.py`

- [ ] **Step 1: Write failing grounding tests**

Add tests that assert:

```python
def test_validate_manifest_rejects_page_grounding_with_element_or_table_id() -> None:
    page_id = uuid4()
    element_id = uuid4()
    region = SemanticRegionAnnotation(
        semantic_type="billing_summary",
        priority="high",
        granite_task="kvp",
        target_schema="invoice",
        grounding=SemanticGroundingRef(kind="page", page_id=page_id, element_id=element_id),
        confidence=0.8,
    )
    with pytest.raises(SemanticAnnotationValidationError, match="Page grounding"):
        validate_manifest(
            _manifest_with_region(region),
            valid_page_ids={page_id},
            valid_element_ids={element_id},
            valid_table_ids=set(),
        )
```

Add equivalent tests for:
- table task with page grounding and `review_required=False`;
- `granite_task != "ignore"` with `target_schema=None`;
- duplicate regions with same grounding, semantic type, and task.

Run: `python -m pytest -q tests/unit/semantic_annotations/test_policy.py`

Expected: FAIL until policy is hardened.

- [ ] **Step 2: Expand allowlists**

Update `ALLOWED_SEMANTIC_TYPES` and `ALLOWED_GRANITE_TASKS` to match the new schema.
Remove chart task values from auto-routing allowlists unless they remain supported
elsewhere intentionally.

- [ ] **Step 3: Add grounding shape validation**

Implement:

```python
def _validate_grounding_shape(region: SemanticRegionAnnotation) -> None:
    grounding = region.grounding
    if grounding.kind == "page" and (grounding.element_id or grounding.table_id):
        raise SemanticAnnotationValidationError("Page grounding must not include element_id or table_id.")
    if grounding.kind == "element" and (grounding.page_id is None or grounding.table_id):
        raise SemanticAnnotationValidationError("Element grounding requires page_id and element_id only.")
    if grounding.kind == "table" and (grounding.page_id is None or grounding.element_id):
        raise SemanticAnnotationValidationError("Table grounding requires page_id and table_id only.")
```

- [ ] **Step 4: Add routing validation**

Implement:

```python
def _validate_routing(region: SemanticRegionAnnotation) -> None:
    if region.granite_task == "ignore":
        return
    if region.target_schema not in {"receipt", "invoice", "medical_eob"}:
        raise SemanticAnnotationValidationError("Routed Granite regions require a supported target schema.")
    if region.granite_task in {"tables_json", "tables_html", "tables_otsl"}:
        if region.grounding.kind != "table" and not region.review_required:
            raise SemanticAnnotationValidationError("Table Granite tasks require table grounding or review.")
```

- [ ] **Step 5: Add duplicate-region validation**

In `validate_manifest`, track:

```python
seen: set[tuple[object, ...]] = set()
key = (
    region.semantic_type,
    region.granite_task,
    region.grounding.kind,
    region.grounding.page_id,
    region.grounding.element_id,
    region.grounding.table_id,
)
if key in seen:
    raise SemanticAnnotationValidationError("Duplicate semantic region.")
seen.add(key)
```

- [ ] **Step 6: Run focused tests**

Run: `python -m pytest -q tests/unit/semantic_annotations/test_policy.py`

Expected: PASS.

## Task 7: Add Gateway Retry For Schema/JSON/Length Failures

**Files:**
- Modify: `lib/semantic_annotations/qwen_gateway.py`
- Test: `tests/unit/semantic_annotations/test_gateways.py`

- [ ] **Step 1: Write failing retry test**

Add a fake client that raises
`ModelProtocolError("Vision model response was truncated before valid JSON completed.")`
once, then returns a valid manifest. Test:

```python
def test_qwen_gateway_retries_once_after_truncated_output() -> None:
    source = _source_with_page_image()

    class RetryClient:
        calls = 0

        def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
            self.calls += 1
            if self.calls == 1:
                raise ModelProtocolError("Vision model response was truncated before valid JSON completed.")
            return VisionGenerateResponse(
                profile_name=QWEN_SEMANTIC_PROFILE,
                model_name="fake-qwen",
                model_version="test",
                source_engine="qwen3_vl_2b",
                prompt_version=request.prompt_version,
                raw_text="{}",
                normalized_json=_semantic_payload(source.pages[0].page_id),
                confidence_json={"overall": 0.8},
                input_sha256=tuple(image.validated_sha256() for image in request.image_inputs),
                latency_ms=1,
            )

    client = RetryClient()
    result = QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    assert client.calls == 2
    assert result.manifest.pages[0].page_id == source.pages[0].page_id
```

Run: `python -m pytest -q tests/unit/semantic_annotations/test_gateways.py::test_qwen_gateway_retries_once_after_truncated_output`

Expected: FAIL because there is no retry.

- [ ] **Step 2: Implement retry wrapper**

In `_generate_for_source`, wrap `client.generate`:

```python
last_error: ModelProtocolError | None = None
for attempt in range(2):
    try:
        return self.client.generate(request)
    except ModelProtocolError as exc:
        last_error = exc
        if not _is_retryable_model_error(exc) or attempt == 1:
            raise
if last_error is not None:
    raise last_error
raise ModelProtocolError("Semantic annotation failed before model response.")
```

Implement `_is_retryable_model_error` for messages containing `truncated`,
`valid JSON`, `semantic annotation schema`, or `page coverage`.

- [ ] **Step 3: Run focused tests**

Run: `python -m pytest -q tests/unit/semantic_annotations/test_gateways.py`

Expected: PASS.

## Task 8: Preserve Atomic Failure Behavior

**Files:**
- Modify: `lib/semantic_annotations/service.py`
- Test: `tests/integration/test_phase8_5_semantic_annotations.py`

- [ ] **Step 1: Add integration test for schema-invalid Qwen output**

Add an integration test that uses `StaticSemanticGateway` to return a manifest with
an unsupported routed target schema or invalid grounding. Assert:

```python
assert load_current_manifest(document_id=document_id, profile_name="qwen3-vl-2b-semantic:v1", quality_mode="smart") is None
```

and:

```sql
SELECT count(*) AS total
FROM pipeline_jobs
WHERE document_id = %s
  AND job_type = 'extract'
```

returns zero.

Run: `STRUCTURA_TEST_DATABASE_URL="$STRUCTURA_TEST_DATABASE_URL" python -m pytest -q tests/integration/test_phase8_5_semantic_annotations.py`

Expected: PASS if the prior atomicity remediation is still intact; otherwise FAIL and fix transaction boundaries before proceeding.

- [ ] **Step 2: Fix only if the integration test fails**

If the test fails, move manifest persistence and targeted Granite job payload creation
into the same transaction boundary used by `SemanticAnnotationService.annotate_document`.
Do not create independent commits inside repository helpers for this path.

- [ ] **Step 3: Run integration test through the canonical runner**

Run: `STRUCTURA_TEST_DATABASE_URL="$STRUCTURA_TEST_DATABASE_URL" python scripts/run_integration_tests.py tests/integration/test_phase8_5_semantic_annotations.py`

Expected: PASS.

## Task 9: Run Private Corpus Smoke

**Files:**
- Use: `scripts/gpu/run_phase8_5_private_corpus.py`
- Use: `/Users/brennanconley/Downloads/MRI Anthem Denial 01-26.pdf`
- Use: `/Users/brennanconley/Downloads/BMW CE-04 600mi run in service and tire service 04-23.pdf`

- [ ] **Step 1: Commit and push code changes**

Run locally after tests pass:

```bash
git add contracts/schemas/semantic_annotation_manifest.v1.schema.json lib/model_runtime/contracts.py lib/model_runtime/clients/_openai_vision.py lib/semantic_annotations/schema.py lib/semantic_annotations/qwen_gateway.py lib/semantic_annotations/policy.py tests/unit/model_runtime/test_qwen_client.py tests/unit/semantic_annotations/test_gateways.py tests/unit/semantic_annotations/test_policy.py tests/integration/test_phase8_5_semantic_annotations.py
git commit -m "Harden Qwen semantic structured output"
git push origin master
```

Expected: push succeeds.

- [ ] **Step 2: Sync GPU checkout**

Run:

```bash
ssh -i /Users/brennanconley/vibecode/infx/ubuntu24_ed25519 bgconley@10.25.0.50 'cd /tank/repos/structura && git pull --ff-only'
```

Expected: GPU checkout reaches the pushed commit.

- [ ] **Step 3: Rebuild affected containers on GPU**

Run on GPU:

```bash
cd /tank/repos/structura
docker compose --profile extraction --profile semantic --profile models-live build api worker-semantic-annotations worker-extraction
```

Expected: build succeeds.

- [ ] **Step 4: Run live model probe**

Run on GPU:

```bash
cd /tank/repos/structura
scripts/gpu/phase8_5_model_smoke.sh --skip-text-embed
```

Expected: Qwen2B, Qwen8B, Granite, and visual embedder probes pass.

- [ ] **Step 5: Run private corpus once**

Run on GPU with the staged PDFs:

```bash
cd /tank/repos/structura
python scripts/gpu/run_phase8_5_private_corpus.py --skip-text-embed --pdf "/srv/structura/tmp/phase8_5_private_corpus/MRI Anthem Denial 01-26.pdf" --pdf "/srv/structura/tmp/phase8_5_private_corpus/BMW CE-04 600mi run in service and tire service 04-23.pdf"
```

Expected:
- Docling parse succeeds for both PDFs.
- Qwen2B semantic annotation succeeds for both PDFs.
- Qwen8B high-quality semantic annotation succeeds for both PDFs.
- Granite targeted extraction jobs are queued from validated regions.
- Visual embedding runs on page images.
- No semantic job fails with invalid/truncated JSON.

## Task 10: Full Verification

**Files:**
- Verify repo-wide.

- [ ] **Step 1: Run local focused tests**

Run:

```bash
python -m pytest -q tests/unit/model_runtime/test_qwen_client.py tests/unit/semantic_annotations/test_gateways.py tests/unit/semantic_annotations/test_policy.py
```

Expected: PASS.

- [ ] **Step 2: Run GPU canonical gates**

Run on GPU:

```bash
cd /tank/repos/structura
ruff format --check .
ruff check .
python scripts/validate_contracts.py
python -m pyright --pythonpath .
python -m mypy lib apps workers scripts
pytest -q tests
make sast
docker run --rm -v "$PWD/apps/web:/app" -w /app node:20-alpine sh -lc 'npm ci && npm run lint && npm run build'
docker compose --profile extraction --profile semantic --profile models-live config -q
```

Expected: all commands pass.

- [ ] **Step 3: Run live browser suite if web/API surfaces changed**

Run from Mac against GPU-hosted web:

```bash
cd /Users/brennanconley/vibecode/structura/apps/web
STRUCTURA_E2E_LIVE=1 STRUCTURA_E2E_BASE_URL=http://10.25.0.50:13000 npx playwright test ../../tests/e2e/phase1-live.spec.ts ../../tests/e2e/phase2-live.spec.ts ../../tests/e2e/phase3-live.spec.ts ../../tests/e2e/phase4-live.spec.ts ../../tests/e2e/phase5-live.spec.ts ../../tests/e2e/phase6-live.spec.ts ../../tests/e2e/phase7-live.spec.ts ../../tests/e2e/phase8-live.spec.ts --workers=1
```

Expected: PASS.

## Self-Review Checklist

- This plan covers schema, prompt, model request, validation, retry, atomicity, and GPU private corpus verification.
- It deliberately does not implement Phase 9.
- It removes the provisional two-region cap by test.
- It treats truncated JSON as retryable failure, not as valid output.
- It keeps Qwen output as routing metadata only.
