# Phase 8.5 Docling-Qwen-Granite Realignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore reliable Phase 8.5 Smart Parse behavior after the Qwen3-VL-4B swap by auditing Docling truth, preserving document-level semantic context, hardening Qwen page-window reconciliation, preventing bad target-schema escalation into Granite, and stabilizing vLLM structured-output usage.

**Architecture:** Docling remains the physical parse authority, but its runtime output must be audited instead of assumed correct. Qwen3-VL-4B remains the Smart Parse semantic planner and may use adaptive multi-page visual fan-in when it satisfies exact Docling page coverage, with one-page windows as a fallback rather than a permanent semantic downgrade. Granite remains region-scoped structured extraction, but only receives canonical target schemas after schema-fit gates pass.

**Tech Stack:** Python, FastAPI workers, PostgreSQL, Docling parse projections, Qwen3-VL-4B via vLLM OpenAI-compatible chat, Granite 4.0 3B Vision via vLLM, JSON Schema validation, pytest, GPU private corpus runner.

---

## Source Findings To Preserve

- The historical Qwen3-VL-2B semantic profile used `max_images_per_request=4` and Compose `{"image":4,"video":0}`.
- The initial Qwen3-VL-4B profile used `max_images_per_request=2`.
- Commit `be330bb` changed Qwen3-VL-4B to `max_images_per_request=1` after BH Photo returned valid semantic JSON covering only one Docling page out of two.
- That one-page cap fixed exact Docling page coverage, but changed the semantic input shape versus Qwen3-VL-2B.
- `_source_for_pages()` currently filters pages, elements, and tables to the image window before `build_docling_context()`, so one-page visual windows also become one-page Docling-context windows.
- `_merge_partial_manifests()` currently chooses the first non-empty `document_type`; this can make page one dominate multi-page document classification.
- `_target_schema_for_region()` currently lets semantic type strongly influence target schema, so a bad Qwen semantic type can send Granite an incorrect canonical schema.
- Granite is region/task extractor, not the document-family referee.
- The OpenAI-compatible vision client currently sends both `response_format: json_schema` and `structured_outputs.json` when schema output is requested, and always sets `max_tokens`.

## Files And Responsibilities

- Modify `lib/semantic_annotations/docling_context.py`: build bounded whole-document context plus focus-page details for Qwen semantic requests.
- Modify `lib/semantic_annotations/qwen_gateway.py`: separate image-window source from document-context source; add adaptive multi-page fan-in with one-page fallback; delegate partial merge to a focused module.
- Create `lib/semantic_annotations/manifest_merge.py`: reconcile partial Qwen manifests by page evidence instead of first non-empty document type.
- Create `lib/semantic_annotations/schema_fit.py`: deterministic anchor checks for invoice, receipt, medical EOB, real estate/title, escrow, dispute, and generic documents.
- Modify `lib/semantic_annotations/target_schema_policy.py`: require schema fit before canonical invoice/receipt/EOB routing; prefer `document_observation` for unsupported or conflicting evidence.
- Modify `lib/semantic_annotations/service.py`: pass source-level schema fit into Granite job selection; preserve review metadata when gating downgrades a target.
- Modify `lib/extraction/granite_prompting.py`: put Granite task tags such as `<tables_json>` at the beginning of table prompts and keep KVP prompts close to Granite/VAREX format.
- Modify `lib/model_runtime/clients/_openai_vision.py`: capability-aware structured-output payload construction; do not send duplicate structured-output mechanisms to the same endpoint.
- Create `scripts/gpu/run_phase8_5_semantic_canary.py`: semantic-only A/B harness for Docling -> Qwen without Granite.
- Create `scripts/gpu/report_phase8_5_docling_canary.py`: Docling-only audit report for private PDFs.
- Extend unit tests under `tests/unit/semantic_annotations/`, `tests/unit/model_runtime/`, and `tests/unit/extraction/`.

---

### Task 1: Add Docling-Only Canary Reporting

**Files:**
- Create: `lib/semantic_annotations/docling_audit.py`
- Create: `scripts/gpu/report_phase8_5_docling_canary.py`
- Test: `tests/unit/semantic_annotations/test_docling_audit.py`

- [ ] **Step 1: Write failing unit tests for Docling audit summaries**

Add tests proving the audit preserves family anchors and table inventory:

```python
def test_docling_audit_finds_real_estate_and_escrow_anchors() -> None:
    source = _source_with_pages(
        [
            "Phenix Title Seller Information Form seller proceeds wiring instructions",
            "UWM Final Escrow Statement escrow account shortage surplus",
        ]
    )

    audit = build_docling_audit(source)

    assert audit.page_count == 2
    assert "seller" in audit.lexical_anchors
    assert "escrow" in audit.lexical_anchors
    assert audit.suggested_family_hints == ("real_estate_title", "mortgage_escrow_statement")
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_docling_audit.py
```

Expected: fail because `lib.semantic_annotations.docling_audit` does not exist.

- [ ] **Step 3: Implement the audit module**

Create a frozen dataclass with fields:

```python
DoclingAudit(
    document_id: UUID,
    page_count: int,
    element_count: int,
    table_count: int,
    page_snippets: tuple[PageAuditSnippet, ...],
    table_summaries: tuple[TableAuditSummary, ...],
    lexical_anchors: tuple[str, ...],
    suggested_family_hints: tuple[str, ...],
)
```

Anchor rules must include at least:

```python
{
    "medical_eob": ("eob", "explanation of benefits", "claim", "patient responsibility", "anthem"),
    "invoice": ("invoice", "amount due", "bill to", "invoice number"),
    "receipt": ("receipt", "subtotal", "tax", "paid", "payment"),
    "retail_order": ("order", "ship to", "order number", "b&h", "bh photo"),
    "real_estate_title": ("title", "seller information", "seller proceeds", "closing", "settlement"),
    "mortgage_escrow_statement": ("escrow", "mortgage", "shortage", "surplus", "uwm"),
    "financial_dispute_form": ("dispute", "transaction", "charge", "unauthorized"),
}
```

- [ ] **Step 4: Implement the GPU report script**

The script must accept:

```bash
scripts/gpu/report_phase8_5_docling_canary.py --document-id <uuid>
scripts/gpu/report_phase8_5_docling_canary.py --pdf "/path/file.pdf"
```

For `--pdf`, it should ingest/parse only when the document is not already present. Output JSON with `document_id`, `page_count`, `element_count`, `table_count`, `lexical_anchors`, `suggested_family_hints`, page snippets, and table summaries.

- [ ] **Step 5: Run tests**

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_docling_audit.py
python -m ruff check lib/semantic_annotations/docling_audit.py scripts/gpu/report_phase8_5_docling_canary.py tests/unit/semantic_annotations/test_docling_audit.py
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add lib/semantic_annotations/docling_audit.py scripts/gpu/report_phase8_5_docling_canary.py tests/unit/semantic_annotations/test_docling_audit.py
git commit -m "Add Phase 8.5 Docling canary audit"
```

---

### Task 2: Add Whole-Document Docling Context With Focus-Page Detail

**Files:**
- Modify: `lib/semantic_annotations/docling_context.py`
- Modify: `tests/unit/semantic_annotations/test_docling_context.py`

- [ ] **Step 1: Write failing tests for whole-document context**

Add coverage proving a focus-page request still includes all-page document outline:

```python
def test_docling_context_keeps_document_outline_for_focus_page() -> None:
    source = _multi_page_source(
        page_texts=[
            "Seller Information Form Phenix Title",
            "Escrow Statement UWM mortgage escrow shortage",
            "Signature instructions",
        ]
    )

    context = build_docling_context(source, focus_page_numbers={2})

    assert context["document"]["pageCount"] == 3
    assert context["document"]["lexicalAnchors"] == ["escrow", "mortgage", "seller", "title"]
    assert [page["pageNumber"] for page in context["document"]["pageOutline"]] == [1, 2, 3]
    assert [page["pageNumber"] for page in context["focusPages"]] == [2]
    assert "Seller Information" in context["document"]["pageOutline"][0]["textSnippet"]
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_docling_context.py::test_docling_context_keeps_document_outline_for_focus_page
```

Expected: fail because `focus_page_numbers` is not supported.

- [ ] **Step 3: Extend `build_docling_context`**

Change the signature to:

```python
def build_docling_context(
    source: ExtractionSourceDocument,
    *,
    focus_page_numbers: set[int] | None = None,
) -> dict[str, Any]:
```

Return keys:

```python
{
    "document": {
        "documentId": "...",
        "family": source.family,
        "subtype": source.subtype,
        "title": source.title,
        "originalFilename": source.original_filename,
        "counterpartyDisplay": source.counterparty_display,
        "quality": ...,
        "pageCount": len(source.pages),
        "elementCount": len(source.elements),
        "tableCount": len(source.tables),
        "lexicalAnchors": [...],
        "pageOutline": [...],
        "tableInventory": [...],
    },
    "focusPages": [...],
}
```

Keep existing bounds for snippets. Do not include storage paths.

- [ ] **Step 4: Preserve backward compatibility expectations**

Update existing tests that read `context["pages"]` to read `context["focusPages"]`, or keep `pages` as an alias to `focusPages` for one release if that reduces blast radius.

- [ ] **Step 5: Run tests**

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_docling_context.py tests/unit/semantic_annotations/test_gateways.py
python -m ruff check lib/semantic_annotations/docling_context.py tests/unit/semantic_annotations/test_docling_context.py
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add lib/semantic_annotations/docling_context.py tests/unit/semantic_annotations/test_docling_context.py tests/unit/semantic_annotations/test_gateways.py
git commit -m "Preserve whole-document Docling context for semantic windows"
```

---

### Task 3: Separate Qwen Image Windowing From Docling Context

**Files:**
- Modify: `lib/semantic_annotations/qwen_gateway.py`
- Test: `tests/unit/semantic_annotations/test_gateways.py`

- [ ] **Step 1: Write failing test for one-page image plus whole-document prompt**

Add a fake client assertion:

```python
def test_one_page_qwen_window_receives_whole_document_docling_context() -> None:
    source = _source_with_three_page_images(
        page_texts=[
            "Seller Information Form",
            "Escrow Statement",
            "Signature page",
        ]
    )
    client = RecordingSemanticVisionClient(...)

    QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    assert [len(request.image_inputs) for request in client.requests] == [1, 1, 1]
    assert all('"pageCount": 3' in request.prompt for request in client.requests)
    assert '"focusPages"' in client.requests[1].prompt
    assert "Seller Information Form" in client.requests[1].prompt
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_gateways.py::test_one_page_qwen_window_receives_whole_document_docling_context
```

Expected: fail because `_source_for_pages()` narrows Docling context to the chunk.

- [ ] **Step 3: Change Qwen request plumbing**

Update methods:

```python
def _generate_manifest_for_source(
    self,
    source: ExtractionSourceDocument,
    *,
    quality_mode: str,
    profile_name: str,
    prompt_version: str,
    context_source: ExtractionSourceDocument | None = None,
    focus_page_numbers: set[int] | None = None,
) -> DocumentSemanticManifest:
```

For page windows, call:

```python
self._generate_manifest_for_source(
    chunk_source,
    quality_mode=quality_mode,
    profile_name=profile_name,
    prompt_version=prompt_version,
    context_source=source,
    focus_page_numbers={page.page_number for page in chunk_source.pages},
)
```

`_image_inputs()` must still use `chunk_source`. `_prompt()` must use `context_source or source`.

- [ ] **Step 4: Run tests**

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_gateways.py tests/unit/semantic_annotations/test_docling_context.py
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add lib/semantic_annotations/qwen_gateway.py tests/unit/semantic_annotations/test_gateways.py
git commit -m "Decouple Qwen image windows from Docling document context"
```

---

### Task 4: Replace First-Document-Type Merge With Evidence Reconciliation

**Files:**
- Create: `lib/semantic_annotations/manifest_merge.py`
- Modify: `lib/semantic_annotations/qwen_gateway.py`
- Test: `tests/unit/semantic_annotations/test_manifest_merge.py`

- [ ] **Step 1: Write failing merge tests**

Required tests:

```python
def test_merge_does_not_let_first_page_receipt_vote_dominate_escrow_document() -> None:
    partials = [
        _partial(document_type="receipt", page_hint="receipt", confidence=0.55),
        _partial(document_type="mortgage_escrow_statement", page_hint="mortgage_escrow_statement", confidence=0.86),
    ]
    source = _source_with_text("UWM Final Escrow Statement escrow shortage mortgage")

    merged = merge_partial_semantic_manifests(source, partials, quality_mode="smart", profile_name="qwen3-vl-4b-semantic:v1", prompt_version="phase8_5-semantic-smart-v2")

    assert merged.manifest["document_type"] == "mortgage_escrow_statement"
```

```python
def test_merge_downgrades_conflicting_low_confidence_votes_to_generic_form() -> None:
    partials = [
        _partial(document_type="receipt", confidence=0.51),
        _partial(document_type="medical_eob", confidence=0.52),
    ]
    source = _source_with_text("scan page handwritten unclear")

    merged = merge_partial_semantic_manifests(...)

    assert merged.manifest["document_type"] == "generic_form"
    assert merged.review_required is True
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_manifest_merge.py
```

Expected: fail because module does not exist.

- [ ] **Step 3: Implement merge module**

Rules:

- Preserve exact page annotations and region annotations.
- Compute votes from `partial.manifest["document_type"]`, page `document_type_hint`, and Docling audit anchors.
- Prefer Docling audit anchors when they clearly identify real-estate/title, escrow, dispute, or medical EOB.
- Require confidence/evidence threshold for canonical invoice/receipt/medical EOB.
- Downgrade conflicts to `generic_form` or `document_observation`.
- Add `confidence["document_type_votes"]` and `confidence["document_type_decision_reason"]`.

- [ ] **Step 4: Wire Qwen gateway to the merge module**

Replace the inline `_merge_partial_manifests()` body with a call to `merge_partial_semantic_manifests(...)`.

- [ ] **Step 5: Run tests**

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_manifest_merge.py tests/unit/semantic_annotations/test_gateways.py tests/unit/semantic_annotations/test_policy.py
python -m ruff check lib/semantic_annotations/manifest_merge.py lib/semantic_annotations/qwen_gateway.py tests/unit/semantic_annotations/test_manifest_merge.py
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add lib/semantic_annotations/manifest_merge.py lib/semantic_annotations/qwen_gateway.py tests/unit/semantic_annotations/test_manifest_merge.py tests/unit/semantic_annotations/test_gateways.py
git commit -m "Reconcile Qwen semantic page-window document type"
```

---

### Task 5: Make Qwen3-VL-4B Fan-In Adaptive Instead Of Permanently One Page

**Files:**
- Modify: `lib/model_runtime/profiles.py`
- Modify: `compose.yaml`
- Modify: `lib/semantic_annotations/qwen_gateway.py`
- Test: `tests/unit/model_runtime/test_profiles.py`
- Test: `tests/unit/test_compose_model_profiles.py`
- Test: `tests/unit/semantic_annotations/test_gateways.py`

- [ ] **Step 1: Write failing adaptive fan-in tests**

Add tests:

```python
def test_qwen4_uses_profile_fan_in_first_and_falls_back_to_single_page_on_coverage_error() -> None:
    source = _source_with_two_page_images()
    client = CoverageFailThenSinglePageSuccessClient()

    result = QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    assert [len(request.image_inputs) for request in client.requests] == [2, 1, 1]
    assert len(result.manifest.pages) == 2
    assert result.manifest.confidence["fallback_reason"] == "page_coverage"
```

```python
def test_qwen4_keeps_multi_page_result_when_coverage_is_exact() -> None:
    source = _source_with_two_page_images()
    client = MultiPageCoverageSuccessClient()

    result = QwenSemanticAnnotationGateway(client=client).annotate(source, quality_mode="smart")

    assert [len(request.image_inputs) for request in client.requests] == [2]
    assert len(result.manifest.pages) == 2
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_gateways.py::test_qwen4_uses_profile_fan_in_first_and_falls_back_to_single_page_on_coverage_error
```

Expected before implementation: fail because the profile starts directly at one
image. Current implementation restores four-image primary fan-in with one-page
fallback on page-coverage failure.

- [x] **Step 3: Restore Qwen3-VL-4B primary fan-in to four images**

Set:

```python
max_images_per_request=4
```

for `QWEN_SEMANTIC_PROFILE` in `lib/model_runtime/profiles.py`.

Set Compose:

```yaml
STRUCTURA_VLLM_LIMIT_MM_PER_PROMPT: '{"image":4,"video":0}'
```

for `model-qwen-semantic`.

Four images is the current default because it matches the historical 2B semantic
fan-in shape; one-page windows are retained only as the exact-page-coverage
fallback.

- [x] **Step 4: Add page-coverage fallback**

In `QwenSemanticAnnotationGateway.annotate()`:

- Try profile fan-in first.
- If `_generate_manifest_for_source()` raises a retryable page-coverage validation error, retry with one-page windows.
- Do not fallback for non-coverage schema violations that indicate contract drift.
- Record fallback in `manifest.confidence`.

- [ ] **Step 5: Run tests**

Run:

```bash
python -m pytest -q tests/unit/model_runtime/test_profiles.py tests/unit/test_compose_model_profiles.py tests/unit/semantic_annotations/test_gateways.py
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add lib/model_runtime/profiles.py compose.yaml lib/semantic_annotations/qwen_gateway.py tests/unit/model_runtime/test_profiles.py tests/unit/test_compose_model_profiles.py tests/unit/semantic_annotations/test_gateways.py
git commit -m "Make Qwen3-VL-4B semantic fan-in adaptive"
```

---

### Task 6: Add Schema-Fit Gates Before Granite Job Enqueue

**Files:**
- Create: `lib/semantic_annotations/schema_fit.py`
- Modify: `lib/semantic_annotations/target_schema_policy.py`
- Modify: `lib/semantic_annotations/service.py`
- Test: `tests/unit/semantic_annotations/test_schema_fit.py`
- Test: `tests/unit/semantic_annotations/test_target_schema_policy.py`
- Test: `tests/unit/semantic_annotations/test_service.py`

- [ ] **Step 1: Write failing tests**

Required behaviors:

```python
def test_escrow_anchors_block_medical_eob_target_schema() -> None:
    source = _source_with_text("UWM Final Escrow Statement mortgage escrow shortage")
    region = _region(semantic_type="denial_or_coverage_decision", target_schema="medical_eob")

    schema = target_schema_for_region_with_fit(region, source)

    assert schema == "document_observation"
```

```python
def test_claim_anchors_allow_medical_eob() -> None:
    source = _source_with_text("Anthem denial claim patient responsibility explanation of benefits")
    region = _region(semantic_type="denial_or_coverage_decision", target_schema="medical_eob")

    schema = target_schema_for_region_with_fit(region, source)

    assert schema == "medical_eob"
```

```python
def test_seller_information_routes_to_document_observation() -> None:
    source = _source_with_text("Phenix Title Seller Information seller proceeds closing")
    region = _region(semantic_type="seller_information_block", target_schema="receipt")

    schema = target_schema_for_region_with_fit(region, source)

    assert schema == "document_observation"
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_schema_fit.py tests/unit/semantic_annotations/test_target_schema_policy.py tests/unit/semantic_annotations/test_service.py
```

Expected: fail before `schema_fit.py` exists and before service gating is wired.

- [ ] **Step 3: Implement schema fit**

Create:

```python
@dataclass(frozen=True)
class SchemaFitDecision:
    requested_schema: str | None
    permitted_schema: str | None
    decision: Literal["allow", "downgrade", "block"]
    reason: str
    anchors: tuple[str, ...]
```

Implement:

```python
def evaluate_schema_fit(source: ExtractionSourceDocument, requested_schema: str | None) -> SchemaFitDecision:
```

Rules:

- `medical_eob` requires at least two anchors from claim/EOB/insurer/patient responsibility/denial.
- `invoice` requires invoice/bill/amount due/invoice number anchors.
- `receipt` requires receipt/payment/subtotal/tax/paid/merchant/order anchors, but must downgrade if escrow/title anchors dominate.
- `document_observation` is always allowed for useful unsupported documents.
- Conflicting real-estate/title/escrow/dispute anchors downgrade canonical schemas to `document_observation`.

- [ ] **Step 4: Wire service**

In `_target_schema_for_region(region, source)`, call schema fit after `preferred_target_schema(...)`. If downgraded, return `document_observation` and preserve a reason in region/job metadata.

- [ ] **Step 5: Run tests**

Run:

```bash
python -m pytest -q tests/unit/semantic_annotations/test_schema_fit.py tests/unit/semantic_annotations/test_target_schema_policy.py tests/unit/semantic_annotations/test_service.py
python -m ruff check lib/semantic_annotations/schema_fit.py lib/semantic_annotations/target_schema_policy.py lib/semantic_annotations/service.py
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add lib/semantic_annotations/schema_fit.py lib/semantic_annotations/target_schema_policy.py lib/semantic_annotations/service.py tests/unit/semantic_annotations/test_schema_fit.py tests/unit/semantic_annotations/test_target_schema_policy.py tests/unit/semantic_annotations/test_service.py
git commit -m "Gate Granite target schemas by document evidence"
```

---

### Task 7: Harden Granite Prompting And vLLM Structured Output

**Files:**
- Modify: `lib/extraction/granite_prompting.py`
- Modify: `lib/model_runtime/clients/_openai_vision.py`
- Modify: `lib/model_runtime/contracts.py`
- Test: `tests/unit/extraction/test_granite_prompting.py`
- Test: `tests/unit/model_runtime/test_qwen_client.py`
- Test: `tests/unit/model_runtime/test_granite_client.py`

- [ ] **Step 1: Write failing prompt tests**

```python
def test_granite_table_prompt_starts_with_tables_json_tag() -> None:
    prompt = granite_prompt(
        source=_source(),
        schema_name="receipt",
        route_profile="docling_plus_granite_structured",
        semantic_task=_task(semantic_type="receipt_line_item_table", granite_task="tables_json"),
        model_output_schema=_receipt_line_items_schema(),
    )

    assert prompt.startswith("<tables_json>")
```

- [ ] **Step 2: Write failing structured-output payload tests**

Add tests proving only one structured-output mechanism is sent:

```python
def test_openai_vision_payload_uses_response_format_without_structured_outputs_duplicate() -> None:
    payload = _openai_payload(..., use_structured_output=True, structured_output_mode="response_format")

    assert "response_format" in payload
    assert "structured_outputs" not in payload
```

```python
def test_openai_vision_payload_can_use_structured_outputs_without_response_format_schema() -> None:
    payload = _openai_payload(..., use_structured_output=True, structured_output_mode="structured_outputs")

    assert payload["structured_outputs"]["json"]
    assert payload.get("response_format") != {"type": "json_schema"}
```

- [ ] **Step 3: Implement Granite prompt change**

For table regions, prompt must start:

```text
<tables_json>
Extract only the line/service rows visible in the grounded table or region.
...
```

Do not prepend generic prose before the tag.

- [ ] **Step 4: Implement structured-output mode**

Add a request field or profile setting:

```python
structured_output_mode: Literal["response_format", "structured_outputs", "json_object"] = "response_format"
```

Do not send both `response_format: json_schema` and `structured_outputs.json` in the same request.

Keep `max_tokens` for now because vLLM/OpenAI-compatible servers often require an output cap, but record truncation through `finish_reason == "length"` and schema-specific cap telemetry. Do not remove `max_tokens` without a GPU endpoint proof that the server accepts omitted caps and behaves better.

- [ ] **Step 5: Run tests**

Run:

```bash
python -m pytest -q tests/unit/extraction/test_granite_prompting.py tests/unit/model_runtime/test_qwen_client.py tests/unit/model_runtime/test_granite_client.py
python -m ruff check lib/extraction/granite_prompting.py lib/model_runtime/clients/_openai_vision.py lib/model_runtime/contracts.py
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add lib/extraction/granite_prompting.py lib/model_runtime/clients/_openai_vision.py lib/model_runtime/contracts.py tests/unit/extraction/test_granite_prompting.py tests/unit/model_runtime/test_qwen_client.py tests/unit/model_runtime/test_granite_client.py
git commit -m "Harden Granite prompts and structured-output payloads"
```

---

### Task 8: Add Semantic-Only A/B Canary Harness

**Files:**
- Create: `scripts/gpu/run_phase8_5_semantic_canary.py`
- Test: `tests/unit/scripts/test_phase8_5_semantic_canary.py`

- [ ] **Step 1: Write failing test for canary command construction**

Test that the harness supports:

```bash
--mode qwen3-vl-4b-current
--mode qwen3-vl-4b-adaptive
--mode qwen3-vl-2b-historical
--skip-granite
--json-output <path>
```

- [ ] **Step 2: Implement the harness**

For each PDF/document:

- Ensure Docling parse exists.
- Run Docling audit.
- Run semantic annotation only.
- Do not enqueue Granite extraction.
- Emit JSON with:
  - document ID and filename
  - Docling page/element/table counts
  - Docling anchors and family hints
  - Qwen profile/model/prompt version
  - request image fan-in sequence
  - fallback reason if one-page retry occurred
  - merged document type
  - page document hints
  - region semantic types
  - region target schemas
  - target-schema gate decisions

- [ ] **Step 3: Run tests**

Run:

```bash
python -m pytest -q tests/unit/scripts/test_phase8_5_semantic_canary.py
python -m ruff check scripts/gpu/run_phase8_5_semantic_canary.py tests/unit/scripts/test_phase8_5_semantic_canary.py
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add scripts/gpu/run_phase8_5_semantic_canary.py tests/unit/scripts/test_phase8_5_semantic_canary.py
git commit -m "Add Phase 8.5 semantic-only canary harness"
```

---

### Task 9: GPU Canary Gates Before Full Pipeline

**Files:**
- Modify: `STRUCTURA_PHASE_8_5_IMPLEMENTATION_PLAN.md`
- Modify: `AGENTS.md`
- Modify: `.wolf/memory.md`
- Modify: `.wolf/cerebrum.md`
- Modify: `.wolf/anatomy.md`
- Modify: `.wolf/buglog.json`

- [ ] **Step 1: Push and pull to GPU**

Run locally:

```bash
git push origin master
ssh -i /Users/brennanconley/vibecode/infx/ubuntu24_ed25519 bgconley@10.25.0.50 'git -C /tank/repos/structura pull --ff-only origin master'
```

- [ ] **Step 2: Rebuild affected services on GPU**

Run on GPU node:

```bash
cd /tank/repos/structura
docker compose --profile extraction --profile semantic --profile visual build api worker-extraction worker-semantic-annotations worker-visual-embeddings
docker compose --profile extraction --profile semantic --profile visual up -d --force-recreate api worker-extraction worker-semantic-annotations worker-visual-embeddings
docker compose --profile models-live --profile visual-embed-live up -d --force-recreate model-qwen-semantic model-granite model-vl-embed
```

- [ ] **Step 3: Run live model probes**

Run:

```bash
/tank/venvs/structura/bin/python scripts/gpu/probe_phase8_5_live_models.py \
  --skip-qwen --skip-text-embed \
  --qwen-semantic-url http://127.0.0.1:8104 \
  --qwen-semantic-model Qwen/Qwen3-VL-4B-Instruct \
  --granite-url http://127.0.0.1:8101 \
  --granite-model ibm-granite/granite-4.0-3b-vision \
  --visual-embed-url http://127.0.0.1:8103 \
  --visual-embed-model Qwen/Qwen3-VL-Embedding-2B
```

Expected: all live inference probes complete.

- [ ] **Step 4: Run Docling-only canary on private PDFs**

Run for the private corpus PDFs:

```bash
/tank/venvs/structura/bin/python scripts/gpu/report_phase8_5_docling_canary.py \
  --pdf "/Users/brennanconley/Downloads/Phenix Title Seller Info 032924.pdf" \
  --pdf "/Users/brennanconley/Downloads/UWM Final Escrow Statement 4-29-24.pdf" \
  --pdf "/Users/brennanconley/Downloads/BH Photo desktop tripod order.pdf" \
  --json-output /home/bgconley/structura_private_corpus/phase8_5_docling_canary.json
```

Expected:

- Phenix exposes seller/title/closing anchors.
- UWM exposes escrow/mortgage/statement anchors.
- BH Photo exposes order/merchant/line-item/table or retail-order anchors.

- [ ] **Step 5: Run semantic-only A/B canary**

Run:

```bash
/tank/venvs/structura/bin/python scripts/gpu/run_phase8_5_semantic_canary.py \
  --mode qwen3-vl-4b-adaptive \
  --pdf "/Users/brennanconley/Downloads/BH Photo desktop tripod order.pdf" \
  --pdf "/Users/brennanconley/Downloads/Phenix Title Seller Info 032924.pdf" \
  --pdf "/Users/brennanconley/Downloads/UWM Final Escrow Statement 4-29-24.pdf" \
  --pdf "/Users/brennanconley/Downloads/MRI Anthem Denial 01-26.pdf" \
  --pdf "/Users/brennanconley/Downloads/BMW CE-04 600mi run in service and tire service 04-23.pdf" \
  --json-output /home/bgconley/structura_private_corpus/phase8_5_semantic_canary.json
```

Expected:

- Phenix does not route as `receipt`.
- UWM does not route as `medical_eob`.
- Anthem may route as `medical_eob`.
- BMW routes service line-item regions.
- BH Photo routes retail order/receipt candidates without page-coverage failure.

- [ ] **Step 6: Only then run full pipeline**

Run the existing private corpus runner after semantic-only canary passes. Full-pipeline success criteria:

- Qwen3-VL 8B calls remain zero.
- No document-quality ambiguity becomes `pipeline_failed`.
- Granite receives no incorrect canonical target schema when schema-fit gates block it.
- Line-item outputs are preserved after summary/payment regions finish.
- Visual embedding remains co-resident with Granite on GPU1 if live probes and memory allow it.

- [ ] **Step 7: Update docs and OpenWolf**

Record the new rule:

```text
Qwen3-VL-4B Smart Parse uses adaptive semantic fan-in: try profile multi-image fan-in, require exact Docling page coverage, and fallback to one-page visual windows with whole-document Docling context when coverage fails. One-page visual windows are a reliability fallback, not the semantic default.
```

- [ ] **Step 8: Commit documentation**

```bash
git add STRUCTURA_PHASE_8_5_IMPLEMENTATION_PLAN.md AGENTS.md .wolf/memory.md .wolf/cerebrum.md .wolf/anatomy.md .wolf/buglog.json
git commit -m "Document Phase 8.5 semantic canary gates"
```

---

## Definition Of Done

- Docling parse output is audited before blaming Qwen or Granite.
- Qwen3-VL-4B is no longer permanently one-page by design; it uses adaptive fan-in and only falls back when exact page coverage fails.
- One-page fallback still receives whole-document Docling context.
- Page-window merge reconciles document type by evidence and page votes instead of first non-empty value.
- Granite canonical target schemas are gated by document evidence.
- Granite table prompts start with the task tag expected by the model card.
- vLLM structured-output requests use one structured-output mechanism per endpoint.
- Private semantic canary proves Phenix, UWM, BH Photo, Anthem, and BMW route correctly before full extraction.
- Full private corpus can run without Qwen3-VL 8B, without fake invoice/EOB promotion, and without losing line-item candidates.

## Research Sources

- Qwen3-VL-4B model card: https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct
- vLLM structured outputs: https://docs.vllm.ai/en/latest/features/structured_outputs/
- Granite 4.0 3B Vision: https://huggingface.co/ibm-granite/granite-4.0-3b-vision
- Granite Vision repo: https://github.com/ibm-granite/granite-vision-models
- Docling document model: https://docling-project.github.io/docling/concepts/docling_document/
- Docling extraction examples: https://docling-project.github.io/docling/examples/extraction/
- VAREX: https://arxiv.org/html/2603.15118v1
- vLLM issue 13038: https://github.com/vllm-project/vllm/issues/13038
- vLLM issue 14151: https://github.com/vllm-project/vllm/issues/14151
- vLLM issue 15236: https://github.com/vllm-project/vllm/issues/15236
- Qwen3-VL issue 1652: https://github.com/QwenLM/Qwen3-VL/issues/1652
- Reducto extraction best practices: https://docs.reducto.ai/extraction/best-practices-extract
- Reducto citations: https://docs.reducto.ai/v/legacy/extraction/citations
- Alan production document pipeline: https://medium.com/alan/lessons-from-running-an-llm-document-processing-pipeline-in-production-33d87f99cdb1
- Invoice prompt hardening: https://thomas-wiegold.com/blog/building-reliable-invoice-extraction-prompts/
