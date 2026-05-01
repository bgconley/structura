# Phase 8.5 Granite Runtime And Routing Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent ambiguous receipt/observation routing from creating runaway Granite retries while preserving the successful Docling + Qwen3-VL-8B FP8 + Granite extraction path.

**Architecture:** Keep the Phase 8.5 ownership boundaries intact: Docling supplies physical structure, Qwen supplies semantic inventory/routing, Docling structural targets supplement Qwen when evidence is strong, Granite extracts bounded task-specific candidates, and validators/review policy decide promotion. The McDonald's receipt failure is not evidence that restaurant receipts should avoid receipt line-item extraction; it is evidence that the Docling lexical audit incorrectly allowed ordinary receipt language to satisfy `financial_dispute_form`.

**Tech Stack:** Python 3.12, pytest, Postgres pipeline job ledger, Qwen semantic annotations, Granite 4.0 Vision OpenAI-compatible gateway, vLLM model services.

---

## Current Failure Model

The interrupted corpus run showed this chain:

1. `Scan Sep 10, 2025 at 13.34.pdf` is a McDonald's restaurant receipt.
2. Docling/Qwen receipt routing was directionally correct.
3. The Docling anchor audit also inferred `financial_dispute_form` from generic terms such as `transaction` and `charge`.
4. `lib/semantic_annotations/docling_targets.py` added a `dispute_reason_block` observation target.
5. Granite received both legitimate receipt tasks and a false dispute/observation task.
6. Granite timed out on expensive page-level jobs.
7. `workers/extraction/worker.py` marked `ModelTimeoutError` retryable.
8. The private corpus drain loop reclaimed failed jobs inside the same document run while vLLM continued decoding abandoned requests.

This plan fixes the root causes without overfitting to one PDF:

- generic receipt/payment terms cannot create financial-dispute routing without a true dispute trigger;
- restaurant/retail receipts can still produce line-item candidates even when Docling does not produce a table;
- Granite gets task-specific request budgets instead of one global large budget;
- model timeouts do not immediately retry into a GPU saturation loop;
- the private corpus harness stops and captures diagnostics when model-runtime failure appears.

## Anti-Patterns

Do not implement any of these:

- Do not special-case the filename `Scan Sep 10, 2025 at 13.34.pdf`.
- Do not disable receipt line-item extraction merely because Docling table count is zero.
- Do not make Qwen canonical or let Qwen output bypass validators.
- Do not suppress Docling structural targets globally; fix the evidence gates.
- Do not retry Granite timeouts immediately inside the same corpus drain.
- Do not solve runtime saturation by removing Granite/visual-embed co-residency without measured evidence.
- Do not reintroduce Phase 4 heuristic document-family overwrite behavior.

## File Map

- Modify: `lib/semantic_annotations/docling_audit.py`
  - Add required-anchor semantics for observation families, especially `financial_dispute_form`.
- Modify: `lib/semantic_annotations/schema_fit.py`
  - Reuse the same required-anchor semantics when deciding whether Docling anchors can support a schema.
- Modify: `lib/semantic_annotations/docling_targets.py`
  - Stop generating financial-dispute structural targets from generic transaction/charge language.
  - Keep receipt/retail/service table augmentation intact when table evidence exists.
- Modify: `lib/semantic_annotations/service.py`
  - Queue Granite jobs with task-specific max attempts.
  - Preserve existing Qwen/Docling dedupe behavior and tighten only the repeated KVP/observation case.
- Modify: `lib/extraction/gateways/_vision.py`
  - Use task-specific Granite request budgets when calling the model.
- Modify: `lib/extraction/gateways/granite_vision.py`
  - Remove or override the current global `4096` budget in favor of task budgets.
- Create: `lib/extraction/granite_budgets.py`
  - Own `GraniteTaskBudget` and budget selection for Granite task/schema pairs.
- Create: `lib/extraction/model_failure_policy.py`
  - Own retryability decisions for model-runtime failures.
- Modify: `workers/extraction/worker.py`
  - Apply model failure policy instead of retrying every exception.
- Modify: `scripts/gpu/run_phase8_5_private_corpus.py`
  - Stop the corpus document on model timeout by default and emit diagnostics.
- Modify tests:
  - `tests/unit/semantic_annotations/test_docling_audit.py`
  - `tests/unit/semantic_annotations/test_service.py`
  - `tests/unit/extraction/test_model_gateways.py`
  - `tests/unit/extraction/test_worker_failures.py`
  - `tests/unit/test_phase8_5_private_corpus_runner.py`

---

### Task 1: Make Financial-Dispute Anchors Require Real Dispute Evidence

**Files:**
- Modify: `lib/semantic_annotations/docling_audit.py`
- Modify: `lib/semantic_annotations/schema_fit.py`
- Test: `tests/unit/semantic_annotations/test_docling_audit.py`

- [ ] **Step 1: Add failing tests for receipt false positives**

Append these tests to `tests/unit/semantic_annotations/test_docling_audit.py`:

```python
def test_restaurant_receipt_does_not_trigger_financial_dispute_hint() -> None:
    source = _source_with_pages(
        [
            (
                "McDonald's receipt transaction subtotal tax total paid "
                "visa charge payment approval code"
            )
        ]
    )

    audit = build_docling_audit(source)

    assert audit.anchor_counts["receipt"] >= 2
    assert "receipt" in audit.suggested_family_hints
    assert "financial_dispute_form" not in audit.suggested_family_hints
    assert audit.family_tension == ()


def test_financial_dispute_hint_requires_dispute_trigger() -> None:
    source = _source_with_pages(
        [
            (
                "Cardholder dispute form unauthorized transaction charge "
                "merchant amount reason for dispute"
            )
        ]
    )

    audit = build_docling_audit(source)

    assert "financial_dispute_form" in audit.suggested_family_hints
    assert audit.anchor_counts["financial_dispute_form"] >= 3
```

- [ ] **Step 2: Run the focused failing test**

Run:

```bash
pytest tests/unit/semantic_annotations/test_docling_audit.py::test_restaurant_receipt_does_not_trigger_financial_dispute_hint -q
```

Expected: fail because the current audit can treat `transaction` + `charge` as sufficient financial-dispute evidence.

- [ ] **Step 3: Add required-anchor semantics**

In `lib/semantic_annotations/docling_audit.py`, add this near `FAMILY_ANCHORS`:

```python
REQUIRED_HINT_ANCHORS: dict[str, frozenset[str]] = {
    "financial_dispute_form": frozenset(
        {
            "dispute",
            "unauthorized",
            "chargeback",
            "fraud",
        }
    ),
}
```

Expand the financial-dispute anchors so generic support terms remain available but cannot stand alone:

```python
"financial_dispute_form": {
    "dispute": ("dispute", "reason for dispute", "dispute form"),
    "transaction": ("transaction",),
    "charge": ("charge",),
    "unauthorized": ("unauthorized", "not authorized"),
    "chargeback": ("chargeback",),
    "fraud": ("fraud", "fraudulent"),
},
```

Add these helpers:

```python
def family_has_required_hint_fit(family: str, anchors: tuple[str, ...]) -> bool:
    required = REQUIRED_HINT_ANCHORS.get(family)
    if not required:
        return True
    return bool(required.intersection(anchors))


def family_has_suggested_hint(family: str, anchors: tuple[str, ...]) -> bool:
    return len(anchors) >= _hint_threshold(family) and family_has_required_hint_fit(
        family,
        anchors,
    )
```

Change suggested-family construction to:

```python
suggested_family_hints = tuple(
    family
    for family in FAMILY_ANCHORS
    if family_has_suggested_hint(family, anchor_hits.get(family, ()))
)
```

- [ ] **Step 4: Wire schema-fit to the same rule**

In `lib/semantic_annotations/schema_fit.py`, import `family_has_required_hint_fit`:

```python
from lib.semantic_annotations.docling_audit import (
    family_anchor_hits,
    family_has_required_hint_fit,
)
```

Update `_has_required_anchor_fit` so support terms alone do not satisfy financial-dispute fit:

```python
def _has_required_anchor_fit(
    requested: str,
    anchor_hits: dict[str, tuple[str, ...]],
) -> bool:
    allowed = _allowed_anchor_families(requested)
    required_count = _required_anchor_count(requested)
    return any(
        len(anchor_hits.get(family, ())) >= required_count
        and family_has_required_hint_fit(family, anchor_hits.get(family, ()))
        for family in allowed
    )
```

- [ ] **Step 5: Verify audit tests**

Run:

```bash
pytest tests/unit/semantic_annotations/test_docling_audit.py -q
```

Expected: all tests pass, including the new McDonald's-style receipt case.

---

### Task 2: Prevent False Docling Financial-Dispute Structural Targets

**Files:**
- Modify: `lib/semantic_annotations/docling_targets.py`
- Test: `tests/unit/semantic_annotations/test_service.py`

- [ ] **Step 1: Add failing service test for McDonald's receipt structural augmentation**

Append a test to `tests/unit/semantic_annotations/test_service.py` using the existing `_source`, `_manifest`, `RecordingJobs`, and `StaticGateway` helpers:

```python
def test_semantic_service_does_not_add_dispute_target_for_restaurant_receipt() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="receipt",
        text=(
            "McDonald's receipt transaction subtotal tax total paid "
            "visa charge payment approval code"
        ),
    )
    manifest = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        semantic_type="receipt_payment_summary",
        granite_task="kvp",
        target_schema="receipt",
        document_type="receipt",
    )
    jobs = RecordingJobs()

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    semantic_types = [job["payload"].get("semantic_type") for job in jobs.created]
    assert "receipt_payment_summary" in semantic_types
    assert "dispute_reason_block" not in semantic_types
```

- [ ] **Step 2: Run the focused failing test**

Run:

```bash
pytest tests/unit/semantic_annotations/test_service.py::test_semantic_service_does_not_add_dispute_target_for_restaurant_receipt -q
```

Expected: fail before Task 1 implementation or pass after Task 1. If it passes after Task 1, keep the test as regression coverage.

- [ ] **Step 3: Keep observation-family selection tied to suggested hints only**

Review `lib/semantic_annotations/docling_targets.py` after Task 1. `_dominant_observation_family()` and the observation loop should only see `financial_dispute_form` when `audit.suggested_family_hints` contains it. Do not add a parallel raw-anchor check.

- [ ] **Step 4: Verify semantic service tests**

Run:

```bash
pytest tests/unit/semantic_annotations/test_service.py::test_semantic_service_does_not_add_dispute_target_for_restaurant_receipt -q
pytest tests/unit/semantic_annotations/test_service.py::test_semantic_service_uses_docling_table_targets_when_qwen_emits_no_regions -q
pytest tests/unit/semantic_annotations/test_service.py::test_semantic_service_downgrades_weak_receipt_guess_when_title_anchors_dominate -q
```

Expected: all pass. BMW/BH-style Docling table supplementation must remain intact.

---

### Task 3: Add Granite Task Budgets

**Files:**
- Create: `lib/extraction/granite_budgets.py`
- Modify: `lib/extraction/gateways/_vision.py`
- Modify: `lib/extraction/gateways/granite_vision.py`
- Test: `tests/unit/extraction/test_model_gateways.py`

- [ ] **Step 1: Add budget tests**

Replace `test_granite_gateway_uses_larger_output_budget_for_live_structured_json` in `tests/unit/extraction/test_model_gateways.py` with task-specific assertions:

```python
def test_granite_gateway_uses_receipt_line_item_budget() -> None:
    client = FakeVisionClient(
        source_engine="granite_vision_3b",
        profile_name=GRANITE_VISION_PROFILE,
    )
    source = _source_with_page_image()
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="receipt_line_item_table",
        granite_task="tables_json",
        target_schema="receipt",
        expected_fields=("item_description", "quantity", "line_total"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
    )

    GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="receipt",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert client.request is not None
    assert client.request.max_output_tokens == 1024
    assert client.request.timeout_seconds == 90


def test_granite_gateway_uses_small_observation_budget() -> None:
    client = FakeVisionClient(
        source_engine="granite_vision_3b",
        profile_name=GRANITE_VISION_PROFILE,
    )
    source = _source_with_page_image()
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="dispute_reason_block",
        granite_task="kvp",
        target_schema="document_observation",
        expected_fields=("merchant", "amount", "dispute_reason"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
    )

    GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="document_observation",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert client.request is not None
    assert client.request.max_output_tokens == 512
    assert client.request.timeout_seconds == 45
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
pytest tests/unit/extraction/test_model_gateways.py::test_granite_gateway_uses_receipt_line_item_budget -q
pytest tests/unit/extraction/test_model_gateways.py::test_granite_gateway_uses_small_observation_budget -q
```

Expected: fail while Granite still uses the global gateway budget.

- [ ] **Step 3: Create budget module**

Create `lib/extraction/granite_budgets.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from lib.semantic_annotations.models import SemanticExtractionTask


@dataclass(frozen=True)
class GraniteTaskBudget:
    max_output_tokens: int
    timeout_seconds: int
    max_attempts: int


DEFAULT_GRANITE_BUDGET = GraniteTaskBudget(
    max_output_tokens=1024,
    timeout_seconds=60,
    max_attempts=1,
)

LINE_ITEM_TABLE_BUDGET = GraniteTaskBudget(
    max_output_tokens=1024,
    timeout_seconds=90,
    max_attempts=1,
)

SUMMARY_KVP_BUDGET = GraniteTaskBudget(
    max_output_tokens=768,
    timeout_seconds=60,
    max_attempts=1,
)

OBSERVATION_BUDGET = GraniteTaskBudget(
    max_output_tokens=512,
    timeout_seconds=45,
    max_attempts=1,
)


LINE_ITEM_SEMANTIC_TYPES = frozenset(
    {
        "invoice_line_item_table",
        "receipt_line_item_table",
        "retail_order_line_item_table",
        "service_record_line_item_table",
        "covered_services_line_item_table",
        "dispute_transaction_table",
    }
)

OBSERVATION_SEMANTIC_TYPES = frozenset(
    {
        "seller_information_block",
        "escrow_summary",
        "dispute_reason_block",
        "generic_form_kvp",
        "document_observation",
    }
)


def granite_budget_for_task(
    *,
    schema_name: str,
    semantic_task: SemanticExtractionTask | None,
) -> GraniteTaskBudget:
    if semantic_task is None:
        return DEFAULT_GRANITE_BUDGET
    if semantic_task.semantic_type in LINE_ITEM_SEMANTIC_TYPES:
        return LINE_ITEM_TABLE_BUDGET
    if semantic_task.target_schema == "document_observation":
        return OBSERVATION_BUDGET
    if semantic_task.semantic_type in OBSERVATION_SEMANTIC_TYPES:
        return OBSERVATION_BUDGET
    if semantic_task.granite_task == "kvp":
        return SUMMARY_KVP_BUDGET
    return DEFAULT_GRANITE_BUDGET
```

- [ ] **Step 4: Use budgets in the vision gateway**

In `lib/extraction/gateways/_vision.py`, import and use the budget:

```python
from lib.extraction.granite_budgets import granite_budget_for_task
```

Inside `extract()`, before `self.client.generate(...)`:

```python
budget = granite_budget_for_task(
    schema_name=schema_name,
    semantic_task=semantic_task,
)
```

Change request construction:

```python
max_output_tokens=budget.max_output_tokens,
timeout_seconds=budget.timeout_seconds,
```

Add to `raw_output_json`:

```python
"requestBudget": {
    "maxOutputTokens": budget.max_output_tokens,
    "timeoutSeconds": budget.timeout_seconds,
    "maxAttempts": budget.max_attempts,
},
```

- [ ] **Step 5: Remove misleading Granite global budget**

In `lib/extraction/gateways/granite_vision.py`, remove:

```python
max_output_tokens = 4096
```

Do not replace it with another class-level override.

- [ ] **Step 6: Verify gateway tests**

Run:

```bash
pytest tests/unit/extraction/test_model_gateways.py -q
```

Expected: all gateway tests pass with task-specific request budgets.

---

### Task 4: Queue Granite Jobs With Budget Max Attempts

**Files:**
- Modify: `lib/semantic_annotations/service.py`
- Test: `tests/unit/semantic_annotations/test_service.py`

- [ ] **Step 1: Extend the recording job helper if needed**

If `RecordingJobs.create_job()` in `tests/unit/semantic_annotations/test_service.py` does not preserve `max_attempts`, update it to store all keyword arguments:

```python
def create_job(self, **kwargs: object) -> object:
    self.created.append(kwargs)
    return SimpleNamespace(job_id=kwargs["job_id"])
```

- [ ] **Step 2: Add test for max attempts on Granite jobs**

Append:

```python
def test_semantic_service_queues_granite_jobs_with_task_budget_attempts() -> None:
    document_id = uuid4()
    household_id = uuid4()
    page_id = uuid4()
    annotation_id = uuid4()
    source = _source(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        family="receipt",
        text="McDonald's receipt subtotal tax total paid",
    )
    manifest = _manifest(
        document_id=document_id,
        household_id=household_id,
        page_id=page_id,
        semantic_type="receipt_line_item_table",
        granite_task="tables_json",
        target_schema="receipt",
        document_type="receipt",
    )
    jobs = RecordingJobs()

    SemanticAnnotationService(
        source_loader=lambda loaded_document_id: source,
        gateway=StaticGateway(manifest),
        manifest_persister=lambda persisted_manifest: _persist_dynamic_manifest(
            persisted_manifest,
            annotation_id=annotation_id,
        ),
        jobs=jobs,
    ).annotate_document(document_id, quality_mode="smart", requested_by="system")

    assert jobs.created[0]["max_attempts"] == 1
```

- [ ] **Step 3: Run failing test**

Run:

```bash
pytest tests/unit/semantic_annotations/test_service.py::test_semantic_service_queues_granite_jobs_with_task_budget_attempts -q
```

Expected: fail because current job creation relies on the default `max_attempts=5`.

- [ ] **Step 4: Wire budget max attempts into job creation**

In `lib/semantic_annotations/service.py`, import:

```python
from lib.extraction.granite_budgets import granite_budget_for_task
from lib.semantic_annotations.models import SemanticExtractionTask
```

Add a helper near `_region_for_granite_job()`:

```python
def _max_attempts_for_granite_spec(spec: GraniteJobSpec, source: ExtractionSourceDocument) -> int:
    budget = granite_budget_for_task(
        schema_name=spec.target_schema,
        semantic_task=SemanticExtractionTask(
            region_id=spec.region_id,
            annotation_id=spec.annotation_id,
            document_id=source.document_id,
            semantic_type=spec.region.semantic_type,
            granite_task=spec.region.granite_task,
            target_schema=spec.region.target_schema,
            expected_fields=spec.region.expected_fields,
            grounding=spec.region.grounding,
            reason=spec.region.reason,
            confidence=spec.region.confidence,
        ),
    )
    return budget.max_attempts
```

Pass this in both `_enqueue_granite_jobs()` and `_enqueue_granite_jobs_with_cursor()`:

```python
max_attempts=_max_attempts_for_granite_spec(spec, source),
```

- [ ] **Step 5: Verify semantic service tests**

Run:

```bash
pytest tests/unit/semantic_annotations/test_service.py::test_semantic_service_queues_granite_jobs_with_task_budget_attempts -q
pytest tests/unit/semantic_annotations/test_service.py -q
```

Expected: all pass.

---

### Task 5: Make Model Timeout Failures Non-Looping

**Files:**
- Create: `lib/extraction/model_failure_policy.py`
- Modify: `workers/extraction/worker.py`
- Test: `tests/unit/extraction/test_worker_failures.py`

- [ ] **Step 1: Add timeout retry policy test**

Append to `tests/unit/extraction/test_worker_failures.py`:

```python
from lib.model_runtime.http_client import ModelTimeoutError


def test_extraction_worker_does_not_retry_granite_model_timeout(monkeypatch) -> None:
    document_id = uuid4()
    job_id = uuid4()
    job_service = RecordingJobService(
        SimpleNamespace(
            state=SimpleNamespace(job_id=job_id, job_type="extract"),
            document_id=document_id,
            household_id=uuid4(),
            payload={
                "target_schema_name": "receipt",
                "route_profile": "docling_plus_granite_structured",
                "semantic_type": "receipt_line_item_table",
                "semantic_granite_task": "tables_json",
            },
        )
    )
    monkeypatch.setattr(extraction_worker_module.worker, "JobService", lambda: job_service)

    processed = process_next_extraction_job(
        worker_name="worker-extraction-test",
        service=TimeoutExtractionService(),
    )

    assert processed is True
    assert job_service.failed[0]["error_class"] == "ModelTimeoutError"
    assert job_service.failed[0]["retryable"] is False
    assert job_service.failed[0]["details"]["model_failure_policy"] == "do_not_retry_timeout"


class TimeoutExtractionService:
    def extract_document(self, *_args: object, **_kwargs: object) -> object:
        raise ModelTimeoutError("Granite request timed out")
```

- [ ] **Step 2: Run failing test**

Run:

```bash
pytest tests/unit/extraction/test_worker_failures.py::test_extraction_worker_does_not_retry_granite_model_timeout -q
```

Expected: fail because the worker currently passes `retryable=True`.

- [ ] **Step 3: Add failure policy module**

Create `lib/extraction/model_failure_policy.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lib.model_runtime.http_client import ModelTimeoutError


@dataclass(frozen=True)
class ExtractionFailurePolicy:
    retryable: bool
    policy: str


def extraction_failure_policy(
    *,
    payload: dict[str, Any],
    exc: Exception,
) -> ExtractionFailurePolicy:
    route_profile = str(payload.get("route_profile") or "")
    if isinstance(exc, ModelTimeoutError) and route_profile == "docling_plus_granite_structured":
        return ExtractionFailurePolicy(
            retryable=False,
            policy="do_not_retry_timeout",
        )
    return ExtractionFailurePolicy(
        retryable=True,
        policy="default_retryable",
    )
```

- [ ] **Step 4: Use policy in extraction worker**

In `workers/extraction/worker.py`, import:

```python
from lib.extraction.model_failure_policy import extraction_failure_policy
```

In the `except Exception as exc:` block, before `job_service.fail_job(...)`:

```python
failure_policy = extraction_failure_policy(
    payload=claimed.payload,
    exc=exc,
)
```

Change `retryable=True` to:

```python
retryable=failure_policy.retryable,
```

Add to `details`:

```python
"model_failure_policy": failure_policy.policy,
```

- [ ] **Step 5: Verify worker failure tests**

Run:

```bash
pytest tests/unit/extraction/test_worker_failures.py -q
```

Expected: generic exceptions remain retryable, Granite model timeouts do not loop.

---

### Task 6: Stop Private Corpus Runs On Model Timeout

**Files:**
- Modify: `scripts/gpu/run_phase8_5_private_corpus.py`
- Test: `tests/unit/test_phase8_5_private_corpus_runner.py`

- [ ] **Step 1: Update existing runner test expectation**

Rename `test_private_corpus_extraction_drain_reports_failed_region_jobs_without_stopping` to:

```python
def test_private_corpus_extraction_drain_marks_model_timeout_as_fatal(
    monkeypatch,
    capsys,
) -> None:
```

Keep the existing `ModelTimeoutError` failed job fixture, then assert:

```python
try:
    runner._drain_extraction_and_rescue(document_id)
except SystemExit as exc:
    assert exc.code == 2
else:
    raise AssertionError("Model timeout should stop the corpus run by default")
```

Also assert the diagnostic output:

```python
output = capsys.readouterr().out
assert '"stage": "extraction_failures"' in output
assert '"stage": "model_timeout_fatal"' in output
```

- [ ] **Step 2: Run failing test**

Run:

```bash
pytest tests/unit/test_phase8_5_private_corpus_runner.py::test_private_corpus_extraction_drain_marks_model_timeout_as_fatal -q
```

Expected: fail because the runner currently returns failures without stopping.

- [ ] **Step 3: Add fatal-timeout detection**

In `scripts/gpu/run_phase8_5_private_corpus.py`, add:

```python
def _has_model_timeout(failures: list[dict[str, Any]]) -> bool:
    for failure in failures:
        error_json = failure.get("error_json")
        if isinstance(error_json, dict) and error_json.get("error_class") == "ModelTimeoutError":
            return True
    return False
```

After printing `extraction_failures`, add:

```python
if _has_model_timeout(extraction_failures):
    print(
        json.dumps(
            {
                "stage": "model_timeout_fatal",
                "document_id": str(document_id),
                "message": (
                    "Stopping private corpus run because a model timeout indicates "
                    "runtime instability that must not be hidden by retries."
                ),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    raise SystemExit(2)
```

- [ ] **Step 4: Verify runner tests**

Run:

```bash
pytest tests/unit/test_phase8_5_private_corpus_runner.py -q
```

Expected: all pass.

---

### Task 7: Tighten Granite Prompt Boundaries For Observation And Tables

**Files:**
- Modify: `lib/extraction/granite_prompting.py`
- Test: `tests/unit/extraction/test_model_gateways.py`

- [ ] **Step 1: Add prompt assertions**

Add to `tests/unit/extraction/test_model_gateways.py`:

```python
def test_granite_observation_prompt_is_bounded() -> None:
    client = FakeVisionClient(
        source_engine="granite_vision_3b",
        profile_name=GRANITE_VISION_PROFILE,
    )
    source = _source_with_page_image()
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="dispute_reason_block",
        granite_task="kvp",
        target_schema="document_observation",
        expected_fields=("transaction_date", "merchant", "amount", "dispute_reason"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
    )

    GraniteVisionExtractionGateway(client=client).extract(
        source,
        schema_name="document_observation",
        route_profile="docling_plus_granite_structured",
        semantic_task=task,
    )

    assert client.request is not None
    assert "Extract only the requested observation fields" in client.request.prompt
    assert "Do not transcribe paragraphs" in client.request.prompt
    assert "Return null or an empty list when evidence is not visible" in client.request.prompt
```

- [ ] **Step 2: Run failing test**

Run:

```bash
pytest tests/unit/extraction/test_model_gateways.py::test_granite_observation_prompt_is_bounded -q
```

Expected: fail until prompt text is tightened.

- [ ] **Step 3: Tighten prompt language**

In `lib/extraction/granite_prompting.py`, for KVP/observation paths, include:

```python
"Extract only the requested observation fields. "
"Do not transcribe paragraphs or unrelated receipt/legal/payment text. "
"Return null or an empty list when evidence is not visible. "
"Prefer fewer grounded values over broad summaries."
```

For table paths, include:

```python
"If visible rows are not present, return an empty line_items array instead of prose. "
"Do not infer line items from totals, disclaimers, or payment text."
```

- [ ] **Step 4: Verify gateway prompt tests**

Run:

```bash
pytest tests/unit/extraction/test_model_gateways.py -q
```

Expected: all pass.

---

### Task 8: Validate The Full Hardening Slice

**Files:**
- No source changes unless tests reveal a missed seam.

- [ ] **Step 1: Run focused unit suites locally**

Run:

```bash
pytest \
  tests/unit/semantic_annotations/test_docling_audit.py \
  tests/unit/semantic_annotations/test_service.py \
  tests/unit/extraction/test_model_gateways.py \
  tests/unit/extraction/test_worker_failures.py \
  tests/unit/test_phase8_5_private_corpus_runner.py \
  -q
```

Expected: all pass.

- [ ] **Step 2: Run broader static/unit checks locally**

Run:

```bash
ruff check lib workers scripts tests
pytest tests/unit -q
```

Expected: all pass.

- [ ] **Step 3: Commit the hardening changes**

Run:

```bash
git status --short
git add \
  lib/semantic_annotations/docling_audit.py \
  lib/semantic_annotations/schema_fit.py \
  lib/semantic_annotations/docling_targets.py \
  lib/semantic_annotations/service.py \
  lib/extraction/granite_budgets.py \
  lib/extraction/gateways/_vision.py \
  lib/extraction/gateways/granite_vision.py \
  lib/extraction/model_failure_policy.py \
  lib/extraction/granite_prompting.py \
  workers/extraction/worker.py \
  scripts/gpu/run_phase8_5_private_corpus.py \
  tests/unit/semantic_annotations/test_docling_audit.py \
  tests/unit/semantic_annotations/test_service.py \
  tests/unit/extraction/test_model_gateways.py \
  tests/unit/extraction/test_worker_failures.py \
  tests/unit/test_phase8_5_private_corpus_runner.py \
  docs/superpowers/plans/2026-05-01-phase-8-5-granite-runtime-routing-hardening.md
git commit -m "Harden Phase 8.5 Granite routing and timeout policy"
```

Do not add `.DS_Store`, `json`, or unrelated local files.

- [ ] **Step 4: GPU-node validation after push/pull**

On the Mac:

```bash
git push
ssh -i /Users/brennanconley/vibecode/infx/ubuntu24_ed25519 bgconley@10.25.0.50 \
  'cd /tank/repos/structura && git pull --ff-only'
```

On the GPU node, rebuild the affected app images before restarting workers:

```bash
cd /tank/repos/structura
docker compose build --no-cache api worker-extraction worker-semantic-annotations
docker compose up -d api worker-extraction worker-semantic-annotations
```

Keep model containers staged the same way as the current OpenWolf/runtime notes require.

- [ ] **Step 5: GPU smoke order**

Run the failed document first:

```bash
python scripts/gpu/run_phase8_5_private_corpus.py \
  --pdf '/Users/brennanconley/Downloads/Scan Sep 10, 2025 at 13.34.pdf'
```

Expected:

- final family remains receipt/restaurant receipt or receipt-compatible;
- no `financial_dispute_form` structural target unless true dispute trigger text exists;
- no `dispute_reason_block` Granite job;
- receipt payment summary and receipt line item extraction remain allowed;
- no repeated Granite timeout loop;
- if Granite times out, the corpus run stops with `model_timeout_fatal` instead of saturating GPU1.

Then run:

```bash
python scripts/gpu/run_phase8_5_private_corpus.py \
  --pdf '/Users/brennanconley/Downloads/Phenix Title Seller Info 032924.pdf' \
  --pdf '/Users/brennanconley/Downloads/BMW CE-04 600mi run in service and tire service 04-23.pdf' \
  --pdf '/Users/brennanconley/Downloads/BH Photo desktop tripod order.pdf'
```

Expected:

- Phenix remains `real_estate_title`;
- BMW still has service line-item candidates;
- BH still has retail/order line-item candidates;
- no repeated KVP/observation timeout loop.

- [ ] **Step 6: Full corpus gate**

Run the full 11-doc corpus only after the failed-document smoke and three-doc regression pass.

Expected:

- Qwen3-VL-8B FP8 Smart Parse remains the semantic service;
- Docling structural targets supplement Qwen but do not create false dispute routing;
- Granite jobs are bounded by task budget;
- model timeouts are visible operational failures, not hidden retry storms;
- successful sibling region outputs remain persisted and reviewable.

## Self-Review Checklist

- Spec coverage: covers false financial-dispute anchors, Granite request budget, retry policy, corpus harness behavior, prompt boundaries, and GPU validation order.
- Placeholder scan: no `TBD`, `TODO`, or unspecified test expectations.
- Type consistency: new functions are named consistently: `family_has_required_hint_fit`, `granite_budget_for_task`, `extraction_failure_policy`.
- Scope control: no filename-specific rules, no Qwen canonical facts, no Granite bypass of validators, no co-residency changes.
