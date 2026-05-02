# Phase 8.5 Reliable Extraction Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert Phase 8.5 from a model pipeline into a governed extraction platform that processes mixed corpora through closed-world planning, explicit contracts, evidence-grounded candidate admission, conservative promotion, repeatable run manifests, and Phase 9-safe truth surfaces.

**Architecture:** Docling remains physical truth. Qwen3-VL-8B-Instruct-FP8 owns high-recall semantic inventory only. A closed-world planner chooses contracted, grounded, family-compatible extraction tasks before Granite is called. Granite 4.0 3B Vision extracts only from planned region/table inputs. Adapters convert model-output JSON into a `RegionExtractionEnvelope`; evidence concretization, candidate admission, dedupe, and reconciliation decide what becomes reviewable or canonical. Phase 9 consumes accepted truth surfaces directly and review surfaces only with uncertainty labels.

**Tech Stack:** Python 3.12, FastAPI workers, PostgreSQL migrations and JSONB, Pydantic DTOs, JSON Schema model-output contracts, Docling parse tables, Qwen3-VL-8B FP8 semantic annotations, Granite 4.0 3B Vision, pytest, and the GPU resident corpus runner.

---

## Design Locks

- [ ] Keep the production reliability target as bounded deterministic behavior: every document produces evidence-grounded reviewable candidates, bounded partial candidates with explicit review state, or a precise abstention/skip.
- [ ] Treat `0 silently bad candidates` as the central correctness invariant.
- [ ] Keep Qwen semantic-only. Qwen annotations may route and inventory regions; they must not create canonical facts.
- [ ] Keep Granite as a grounded region/table extractor. Granite does not own canonical truth, evidence locators, schema validity, promotion, or review state.
- [ ] Defer Granite replacement or model bakeoff until the control plane is stable. Any bakeoff must run through the same planner, envelope, evidence, admission, and reconciliation gates so model quality is measured separately from app-boundary bugs.
- [ ] Allow safe review warnings, abstentions, and pre-insertion candidate rejections. Do not allow unsafe admission, fabricated canonical output, evidence-less candidates, prompt artifacts, placeholders, or incompatible aggregates.
- [ ] Do not expand canonical families or auto-promotion until the hard invariants, reporting, and repeatability surfaces are stable.

## Files And Ownership

Create or modify these files during implementation:

- [ ] `STRUCTURA_IMPLEMENTATION_PLAN.md` - register this reliability plan and remove stale Phase 8.5 Qwen/HQ-rescue wording.
- [ ] `database/083_phase8_5_reliable_extraction_platform.sql` - planner summaries, plan tasks, and admission telemetry.
- [ ] `lib/semantic_annotations/planner_models.py` - `ExtractionPlanTask`, `ExtractionPlanReport`, planner statuses, planner version metadata.
- [ ] `lib/semantic_annotations/extraction_plan.py` - upgrade from bounded sorter to closed-world planner.
- [ ] `lib/semantic_annotations/extraction_plan_repository.py` - persist plan reports and task rows.
- [ ] `lib/semantic_annotations/service.py` - persist plan reports and enqueue only selected tasks.
- [ ] `lib/extraction/contract_registry.py` - contract resolver, compatibility aliases, fallback policy.
- [ ] `lib/extraction/model_output_schemas.py` - delegate task contract resolution to the registry while preserving public call sites during migration.
- [ ] `lib/extraction/region_envelope.py` - stable internal envelope and evidence primitives.
- [ ] `lib/extraction/evidence_concretizer.py` - attach Structura-owned concrete evidence to envelopes.
- [ ] `lib/extraction/candidate_admission.py` - hard gates, fingerprints, decisions, telemetry payloads.
- [ ] `lib/extraction/model_output_normalization.py` - make adapters emit envelopes and derive `normalized_json` compatibility projections from envelopes.
- [ ] `lib/extraction/extraction_repository.py` - enforce admission decisions before candidate insertion and persist admission events.
- [ ] `lib/extraction/docling_table_quality.py` - deterministic table quality score and routing decision.
- [ ] `lib/extraction/granite_prompting.py` - route table prompts through Docling-primary/table-labeler policies where applicable.
- [ ] `lib/extraction/reconciliation.py` and `lib/extraction/reconciliation_repository.py` - prevent duplicate or incompatible aggregate laundering.
- [ ] `scripts/run_model_corpus.py` and any GPU wrapper script used for the resident corpus - emit run manifests, planner/admission summaries, and repeatability fingerprints.
- [ ] `tests/unit/semantic_annotations/test_extraction_plan.py`
- [ ] `tests/unit/semantic_annotations/test_extraction_plan_repository.py`
- [ ] `tests/unit/extraction/test_contract_registry.py`
- [ ] `tests/unit/extraction/test_region_envelope.py`
- [ ] `tests/unit/extraction/test_evidence_concretizer.py`
- [ ] `tests/unit/extraction/test_candidate_admission.py`
- [ ] `tests/unit/extraction/test_model_output_normalization.py`
- [ ] `tests/unit/extraction/test_docling_table_quality.py`
- [ ] `tests/unit/extraction/test_reconciliation.py`
- [ ] `tests/unit/scripts/test_model_corpus_report.py`

## Task 1: Normalize Phase 8.5 Source Of Truth

- [ ] Update `STRUCTURA_IMPLEMENTATION_PLAN.md` Phase 8.5 required artifacts to include this file:

```text
/Users/brennanconley/vibecode/structura/docs/superpowers/plans/2026-05-01-phase-8-5-reliable-extraction-platform.md
```

- [ ] Replace stale default Smart Parse wording with the active rule:

```text
Qwen3-VL-8B-Instruct-FP8 on model-qwen-semantic is the default Smart Parse semantic planner.
There is no hidden second-pass or escalation Qwen path.
Uncertainty becomes needs_human_review, insufficient_signal, no_extraction_target, or a classified skip.
```

- [ ] Keep Phase 9 explicitly gated until the Phase 8.5 reliability gates pass or unresolved blockers are documented and accepted.
- [ ] Verification: search the active Phase 8.5 planning surfaces for superseded Smart Parse model names or rescue-path language. Expected result: no stale runtime wording remains in active plan surfaces.

## Task 2: Add Queryable Planner And Admission Persistence

- [ ] Add migration `database/083_phase8_5_reliable_extraction_platform.sql`.
- [ ] Create `semantic_extraction_plans`:

```sql
CREATE TABLE IF NOT EXISTS semantic_extraction_plans (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  semantic_annotation_id uuid NOT NULL REFERENCES document_semantic_annotations(id) ON DELETE CASCADE,
  planner_version text NOT NULL,
  prompt_version text,
  model_profile text,
  run_id text,
  status text NOT NULL,

  selected_task_count integer NOT NULL DEFAULT 0,
  skipped_task_count integer NOT NULL DEFAULT 0,
  abstention_count integer NOT NULL DEFAULT 0,
  missing_contract_count integer NOT NULL DEFAULT 0,
  missing_grounding_count integer NOT NULL DEFAULT 0,
  incompatible_schema_count integer NOT NULL DEFAULT 0,
  duplicate_suppressed_count integer NOT NULL DEFAULT 0,

  report_json jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS semantic_extraction_plans_document_idx
  ON semantic_extraction_plans(document_id, created_at DESC);

CREATE INDEX IF NOT EXISTS semantic_extraction_plans_annotation_idx
  ON semantic_extraction_plans(semantic_annotation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS semantic_extraction_plans_run_idx
  ON semantic_extraction_plans(run_id, created_at DESC);
```

- [ ] Create `semantic_extraction_plan_tasks`:

```sql
CREATE TABLE IF NOT EXISTS semantic_extraction_plan_tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_id uuid NOT NULL REFERENCES semantic_extraction_plans(id) ON DELETE CASCADE,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  semantic_region_id uuid,

  semantic_type text NOT NULL,
  granite_task text,
  extractor_backend text,
  resolved_document_type text,
  target_schema text,
  canonical_target_schema text,
  model_output_schema_name text,
  contract_resolution_reason text,
  compatibility_mode text,

  grounding_kind text,
  page_number integer,
  page_id uuid,
  element_id uuid,
  table_id uuid,

  status text NOT NULL,
  skip_reason text,
  review_required boolean NOT NULL DEFAULT true,
  task_json jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS semantic_extraction_plan_tasks_plan_idx
  ON semantic_extraction_plan_tasks(plan_id);

CREATE INDEX IF NOT EXISTS semantic_extraction_plan_tasks_document_idx
  ON semantic_extraction_plan_tasks(document_id, created_at DESC);

CREATE INDEX IF NOT EXISTS semantic_extraction_plan_tasks_status_idx
  ON semantic_extraction_plan_tasks(status, created_at DESC);
```

- [ ] Create `candidate_admission_events` with run/version fields from the start:

```sql
CREATE TABLE IF NOT EXISTS candidate_admission_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  extraction_id uuid REFERENCES document_extractions(id) ON DELETE SET NULL,
  plan_id uuid REFERENCES semantic_extraction_plans(id) ON DELETE SET NULL,
  plan_task_id uuid REFERENCES semantic_extraction_plan_tasks(id) ON DELETE SET NULL,
  semantic_annotation_id uuid REFERENCES document_semantic_annotations(id) ON DELETE SET NULL,
  semantic_region_id uuid REFERENCES semantic_region_annotations(id) ON DELETE SET NULL,

  run_id text,
  planner_version text,
  candidate_gate_version text,
  contract_registry_version text,
  region_envelope_version text,

  candidate_kind text NOT NULL,
  candidate_fingerprint text,
  decision text NOT NULL,
  reasons text[] NOT NULL DEFAULT '{}',

  field_path text,
  semantic_type text,
  model_output_schema_name text,
  source_engine text,
  evidence_concrete boolean,

  payload_json jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS candidate_admission_events_document_idx
  ON candidate_admission_events(document_id, created_at DESC);

CREATE INDEX IF NOT EXISTS candidate_admission_events_decision_idx
  ON candidate_admission_events(decision, created_at DESC);

CREATE INDEX IF NOT EXISTS candidate_admission_events_schema_idx
  ON candidate_admission_events(model_output_schema_name, created_at DESC);

CREATE INDEX IF NOT EXISTS candidate_admission_events_run_idx
  ON candidate_admission_events(run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS candidate_admission_events_plan_task_idx
  ON candidate_admission_events(plan_task_id, created_at DESC)
  WHERE plan_task_id IS NOT NULL;
```

- [ ] Tests:
  - [ ] Migration smoke test verifies all tables and indexes exist.
- [ ] Admission telemetry inserts and queries by document, decision, schema, and run ID.
- [ ] Admission telemetry links candidates to plan ID, plan task ID, semantic annotation ID, and region envelope version.
  - [ ] Plan persistence inserts one summary row plus task rows in a single transaction.

## Task 3: Add Planner DTOs And Report Repository

- [ ] Create `lib/semantic_annotations/planner_models.py`.
- [ ] Define planner status constants:

```text
selected
skipped_missing_contract
skipped_missing_grounding
skipped_incompatible_schema
skipped_no_extraction_target
skipped_budget_exceeded
suppressed_duplicate
abstained
```

- [ ] Define `PlannerVersions` with:

```text
planner_version
prompt_version
model_profile
contract_registry_version
visual_input_plan_version
run_id
```

- [ ] Define `ExtractionPlanTask` with:

```text
document_id
semantic_annotation_id
semantic_region_id
resolved_document_type
persisted_document_family
semantic_document_type
semantic_type
granite_task
target_schema
canonical_target_schema
model_output_schema_name
contract_resolution_reason
compatibility_mode
extractor_backend
page_number
page_id
element_id
table_id
bbox
priority
review_required
status
skip_reason
grounding_summary
visual_plan_summary
budget_policy
retry_policy
task_json
```

- [ ] Define `ExtractionPlanReport` with:

```text
document_id
semantic_annotation_id
versions
status
tasks
selected_tasks
skipped_tasks
abstentions
duplicate_suppressed
summary_counts
report_json
```

- [ ] Add `ExtractionPlanReport.to_summary_row()` and `ExtractionPlanTask.to_task_row()` helpers so repository code does not duplicate count logic.
- [ ] Add `lib/semantic_annotations/extraction_plan_repository.py` to persist the summary and task rows transactionally.
- [ ] Tests:
  - [ ] Count helpers classify every skip and selected task correctly.
  - [ ] Repository persists full report JSON plus queryable summary columns.
  - [ ] Repository preserves `run_id`, `planner_version`, `contract_resolution_reason`, and `compatibility_mode`.

## Task 4: Make The Planner Closed-World

- [ ] Refactor `lib/semantic_annotations/extraction_plan.py` so it emits an `ExtractionPlanReport`, not only a bounded list of Granite enqueue candidates.
- [ ] Planner must answer and persist:

```text
why this region was selected
resolved document type
family/schema compatibility
model-output contract selected
extractor backend selected
grounding locator available
visual input plan selected
budget/fanout decision
review policy
skip or downgrade reason
```

- [ ] Enforce planner hard invariants before enqueue:
  - [ ] No selected/enqueued Granite task without `model_output_schema_name`.
  - [ ] No selected/enqueued Granite task without concrete grounding.
  - [ ] No selected/enqueued incompatible family/schema Granite task.
  - [ ] No `document_header`, boilerplate, blank, or no-target region enqueued as canonical extraction.
  - [ ] No duplicate/overlapping task fanout without an explicit dedupe decision.
  - [ ] No missing-contract task falls through to canonical extraction.
- [ ] Treat the known `document_header` / `medical_eob` missing-contract warning as:

```text
skipped_no_extraction_target
```

or explicit review-only observation fallback. It must not become a Granite job with `model_output_schema_name = null`.

- [ ] Integrate `lib/semantic_annotations/service.py` so only selected tasks enqueue extraction jobs and skipped tasks remain visible in plan persistence.
- [ ] Put planner lineage into every selected extraction job payload:

```json
{
  "plan_id": "...",
  "plan_task_id": "...",
  "semantic_annotation_id": "...",
  "semantic_region_id": "...",
  "model_output_schema_name": "...",
  "canonical_target_schema": "...",
  "compatibility_mode": "...",
  "extractor_backend": "granite_region"
}
```

- [ ] Persist the same lineage on `document_extractions` through nullable columns or metadata:

```text
plan_id
plan_task_id
canonical_target_schema
compatibility_mode
contract_resolution_reason
region_envelope_version
```

- [ ] A selected Granite task for canonical-target extraction must have a model-output contract before enqueue. If no contract exists, the planner must skip, abstain, or downgrade to explicit review-only generic observation fallback. The extraction runtime must not discover missing contracts for selected canonical tasks.
- [ ] Tests:
  - [ ] Missing contract becomes skip/abstention.
  - [ ] Missing grounding becomes skip/abstention.
  - [ ] Incompatible schema becomes skip or review-only downgrade.
  - [ ] `document_header` does not enqueue canonical extraction.
  - [ ] Duplicate region suppression is recorded.
  - [ ] Budget/fanout policy is enforced and visible.

## Task 5: Add Contract Registry, Compatibility Policy, And Aliases

- [ ] Create `lib/extraction/contract_registry.py`.
- [ ] Define:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ContractResolution:
    schema_name: str | None
    exact: bool
    review_only: bool
    reason: str
    compatibility_mode: str | None  # exact, compatible_alias, generic_review_only, missing
    canonical_target_schema: str | None
```

- [ ] Define `CONTRACT_REGISTRY_VERSION = "phase8_5-contract-registry-v1"`.
- [ ] Key exact contracts on:

```text
resolved_document_type
semantic_type
granite_task
target_schema
```

- [ ] Keep schema concepts separate:

```text
target_schema:
  the currently executable extraction/runtime schema, such as receipt or document_observation

canonical_target_schema:
  the family the fact may eventually promote into, such as service_record or retail_order

model_output_schema_name:
  the Granite response shape, such as granite_receipt_payment_summary.v1
```

- [ ] Compatible aliases may reuse model-output schema shapes, but they must not silently change the canonical target family. A receipt-like model-output schema used for `service_record` or `retail_order` remains an alias contract, not a canonical receipt route.

- [ ] Use existing schema names where they already exist under `contracts/model_outputs/`. Current examples include:

```text
granite_receipt_line_items.v1
granite_receipt_payment_summary.v1
granite_payment_summary.v1
granite_retail_order.v1
granite_service_record_line_items.v1
granite_medical_service_lines.v1
granite_healthcare_coverage_decision.v1
granite_dispute_form.v1
granite_real_estate_title_seller_info.v1
granite_mortgage_escrow_statement.v1
granite_generic_kvp.v1
```

- [ ] Record compatible aliases explicitly instead of silently treating them as exact matches. Examples:

```text
retail_order using receipt-like line-item shape -> compatible_alias
service_record using payment-summary shape -> compatible_alias
```

- [ ] Implement safe fallback policy:
  - [ ] Exact contract required for canonical-target extraction.
  - [ ] Generic fallback allowed only for explicit review-only observation tasks.
  - [ ] Generic fallback targets `document_observation`.
  - [ ] `document_observation` compatibility means review-only observation fallback.
  - [ ] `document_observation` fallback must not create canonical family fields, canonical line items, or aggregate family schemas unless a later reconciler explicitly promotes reviewed observations under family-specific policy.
  - [ ] Generic fallback never creates receipt, invoice, EOB, service-record, title, escrow, or retail-order canonical candidates.
  - [ ] Missing contract becomes planner skip or review-only fallback, not runtime surprise.
- [ ] Add family/schema compatibility:

```python
COMPATIBLE_TARGETS = {
    "receipt": {"receipt", "document_observation"},
    "retail_order": {"retail_order", "receipt", "document_observation"},
    "service_record": {"vehicle_service_record", "service_record", "document_observation"},
    "medical_eob": {"medical_eob", "healthcare_coverage_decision", "document_observation"},
    "healthcare_coverage_decision": {"healthcare_coverage_decision", "medical_eob", "document_observation"},
    "real_estate_title": {"real_estate_title", "document_observation"},
    "mortgage_escrow_statement": {"mortgage_escrow_statement", "document_observation"},
    "financial_dispute_form": {"financial_dispute_form", "document_observation"},
    "unsupported_document": set(),
    "generic": {"document_observation"},
}
```

- [ ] Tests:
  - [ ] Exact contract resolves with `compatibility_mode="exact"`.
  - [ ] Alias contract resolves with `compatibility_mode="compatible_alias"`.
  - [ ] Generic fallback resolves only as `review_only=True` and `target_schema=document_observation`.
  - [ ] A service-record payment-summary alias may resolve `granite_receipt_payment_summary.v1`, but `canonical_target_schema` must not become `receipt` unless an explicit family policy allows it.
  - [ ] Missing contract returns `compatibility_mode="missing"` and does not enqueue Granite.
  - [ ] Receipt documents cannot enqueue invoice targets.
  - [ ] Generic documents cannot use receipt or invoice contracts as fallback.
  - [ ] If persisted family is `generic` and Qwen document type is high-confidence receipt with extraction-relevant anchors, `resolved_document_type` is receipt for extraction planning; generic persisted family must not automatically force `document_observation`.

## Task 6: Make Region Envelope The Authoritative Intermediate

- [ ] Create `lib/extraction/region_envelope.py`.
- [ ] Define `EvidenceRef`:

```python
class EvidenceRef(BaseModel):
    document_id: str
    semantic_annotation_id: str | None = None
    semantic_region_id: str | None = None
    page_number: int | None = None
    page_id: str | None = None
    element_id: str | None = None
    table_id: str | None = None
    bbox: list[float] | None = None
    source_text: str | None = None
    source_engine: str
    confidence: float | None = None
```

- [ ] Define `RegionFact`, `RegionLineItem`, `RegionTableRow`, and `RegionExtractionEnvelope` with `extra="forbid"`, including:

```text
document_id
semantic_annotation_id
semantic_region_id
resolved_document_type
semantic_type
target_schema
model_output_schema_name
coverage
facts
line_items
table_rows
observations
warnings
abstentions
```

- [ ] Implement `to_normalization_projection()` so existing `document_extractions.normalization_json` is derived from the envelope during migration.
- [ ] Transition rule:

```text
Granite model-output JSON
-> validate model-output schema
-> adapter creates RegionExtractionEnvelope
-> evidence concretizer runs on envelope
-> artifact/candidate gates run on envelope
-> normalized_json compatibility projection derives from envelope
-> candidate insertion consumes envelope
```

- [ ] Do not keep two independent authoritative paths. As each adapter reaches parity, remove or disable its direct model-output-to-normalized-json candidate path.
- [ ] Persist the envelope initially at:

```text
document_extractions.normalization_json.regionEnvelope
```

- [ ] Tests:
  - [ ] Every current Granite adapter emits a valid `RegionExtractionEnvelope`.
  - [ ] `normalized_json` is derived from the envelope.
  - [ ] Coverage, warnings, and abstentions survive persistence.
  - [ ] Line items and table rows preserve `table_id`, `row_index`, `page_number`, and `semantic_region_id`.
  - [ ] No adapter inserts candidates without passing through the envelope path once parity is enabled.

## Task 7: Centralize Evidence Concretization

- [ ] Create `lib/extraction/evidence_concretizer.py`.
- [ ] Implement `attach_evidence_to_envelope(envelope, ctx)` using planner/task context.
- [ ] Model-provided `source_text` may enrich evidence, but it cannot satisfy concrete locator by itself.
- [ ] Concrete locator must come from Structura-owned context:

```text
semantic_region_id + page_id
semantic_region_id + page_number
table_id
element_id
bbox
Docling table provenance with page locator
```

- [ ] Implement:

```python
def has_concrete_locator(ref: EvidenceRef) -> bool:
    if ref.table_id or ref.element_id or ref.bbox:
        return True
    if ref.semantic_region_id and (ref.page_id or ref.page_number is not None):
        return True
    return False
```

- [ ] Evidence hard invariant:

```text
0 admitted model-backed candidates without concrete evidence.
```

- [ ] Tests:
  - [ ] Empty evidence lists receive Structura-owned evidence refs.
  - [ ] `source_text` alone fails concrete locator checks.
  - [ ] `semantic_region_id + page_number` passes.
  - [ ] `table_id`, `element_id`, and `bbox` pass.
  - [ ] Evidence failures reject candidates before insertion and create admission events.

## Task 8: Add Candidate Admission Gates And Telemetry

- [ ] Create `lib/extraction/candidate_admission.py`.
- [ ] Define candidate decisions:

```text
admitted_review_required
admitted_auto_promotable
rejected_missing_evidence
rejected_artifact
rejected_placeholder
rejected_duplicate
rejected_value_sanity
rejected_family_schema
```

- [ ] Implement prompt/artifact sentinels:

```python
PROMPT_ECHO_PATTERNS = (
    "identify and extract",
    "extract the schema",
    "extruct the schema",
    "tabls schema",
    "table schema",
    "reading order",
    "return only json",
    "matching the schema",
)

PLACEHOLDER_VALUES = {
    "",
    "null",
    "none",
    "n/a",
    "unknown",
    "visible value",
    "example value",
}

PLACEHOLDER_FIELD_NAMES = {
    "visible_field",
    "field",
    "key",
    "value",
}
```

- [ ] Implement line-item gate:

```python
def reject_line_item(item: dict) -> tuple[bool, str | None]:
    text = " ".join(
        str(item.get(key) or "")
        for key in ("description", "category_hint", "unit", "code")
    ).lower()

    if any(pattern in text for pattern in PROMPT_ECHO_PATTERNS):
        return True, "prompt_or_schema_echo"

    numeric_one_count = sum(
        str(item.get(key)) in {"1", "1.0", "1.00", "1.0000"}
        for key in ("quantity", "unit_price", "gross_amount", "net_amount")
    )

    if numeric_one_count >= 2 and ("schema" in text or "rows" in text):
        return True, "fake_schema_line_item"

    if not str(item.get("description") or "").strip():
        return True, "missing_description"

    return False, None


def zero_amount_line_requires_context(item: dict) -> tuple[bool, str | None]:
    amounts = [item.get("gross_amount"), item.get("net_amount"), item.get("unit_price")]
    all_zero_or_missing = all(
        value in (None, "", 0, 0.0, "0", "0.0", "0.00", "0.0000")
        for value in amounts
    )
    if not all_zero_or_missing:
        return False, None

    description = str(item.get("description") or "").strip()
    code = str(item.get("code") or "").strip()
    service_date = str(item.get("service_date") or "").strip()
    category_hint = str(item.get("category_hint") or "").strip()

    if len(description) >= 12 and (
        code or service_date or category_hint or "service" in description.lower()
    ):
        return False, None

    return True, "zero_amount_without_service_context"
```

- [ ] Enforce gates before candidate insertion:
  - [ ] No prompt/schema echo.
  - [ ] No placeholder field/value.
  - [ ] No literal `"null"` observation value.
  - [ ] No model-backed candidate without concrete evidence.
  - [ ] No model-backed semantic-region extraction marked `auto_accepted`.
  - [ ] No incompatible family/schema candidate.
- [ ] Persist a `candidate_admission_events` row for each admitted or rejected candidate, including `run_id`, `planner_version`, `candidate_gate_version`, `contract_registry_version`, `plan_id`, `plan_task_id`, `semantic_annotation_id`, and `region_envelope_version`.
- [ ] Record extraction-level admission summaries even when no candidates are admitted:

```json
{
  "candidateAdmissionSummary": {
    "produced": 4,
    "admitted": 0,
    "rejected": 4,
    "rejectionReasons": {
      "rejected_artifact": 2,
      "rejected_missing_evidence": 2
    }
  }
}
```

- [ ] Store rejection summaries in `normalization_json.rejectedCandidates` only as a compatibility/reporting projection; queryable telemetry lives in the table.
- [ ] Tests:
  - [ ] Prompt echoes are rejected and not inserted.
  - [ ] Schema echoes are rejected and not inserted.
  - [ ] Placeholder fields and values are rejected and not inserted.
  - [ ] Literal null observations are rejected and not inserted.
  - [ ] Missing evidence is rejected and not inserted.
  - [ ] Model-backed candidates default to `needs_review`.
  - [ ] Admission events persist for rejected and admitted candidates.
  - [ ] Admission event version fields are populated.

## Task 9: Add Dedupe At Planner, Candidate, And Reconciliation Layers

- [ ] Planner dedupe:
  - [ ] Suppress duplicate or overlapping semantic regions before enqueue.
  - [ ] Record `duplicate_suppressed_count`.
  - [ ] Persist suppressed tasks with `status=suppressed_duplicate`.
- [ ] Candidate dedupe fingerprints:

```text
Fields:
  field_path + normalized value + source region

Line items:
  normalized description + code + quantity + unit price + gross/net amount
  + currency + table_id + row_index + semantic region

Observations:
  observation_family + semantic_type + normalized field_name
  + normalized value_json + locator
```

- [ ] Implement stable candidate fingerprinting in `candidate_admission.py`.
- [ ] Reconciliation dedupe:
  - [ ] Do not re-emit model candidates as duplicate system aggregate candidates.
  - [ ] Do not create aggregate copies from incompatible source families.
  - [ ] Do not allow duplicate canonical rows from the same evidence source.
  - [ ] System aggregate rows derived from model-backed candidates remain `needs_review` unless a family/field-specific auto-promotion policy explicitly allows promotion and the gold-corpus precision threshold has been met.
- [ ] Tests:
  - [ ] Duplicate fields are rejected or collapsed deterministically.
  - [ ] Duplicate line items from the same table row are rejected or collapsed.
  - [ ] Duplicate observations are rejected or collapsed.
  - [ ] Aggregate generation does not duplicate source region candidates.
  - [ ] Incompatible source family never creates aggregate canonical rows.

## Task 10: Add Docling-Primary Table Quality And Consistency Gates

- [ ] Create `lib/extraction/docling_table_quality.py`.
- [ ] Define:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class DoclingTableQuality:
    table_id: str
    page_number: int
    row_count: int
    column_count: int
    non_empty_cell_ratio: float
    header_confidence: float
    numeric_column_count: int
    bbox_available: bool
    markdown_available: bool
    continuation_risk: bool
    score: float
    route: str
```

- [ ] Implement route policy:

```python
def select_table_extractor(q: DoclingTableQuality) -> str:
    if (
        q.score >= 0.75
        and q.row_count >= 2
        and q.column_count >= 2
        and q.non_empty_cell_ratio >= 0.50
        and not q.continuation_risk
    ):
        return "docling_table_plus_granite_labeler"

    if q.bbox_available and q.markdown_available:
        return "granite_region_with_docling_context"

    return "granite_full_page_review_required"
```

- [ ] Apply Docling-primary table extraction especially to:

```text
receipts
retail orders
service records
medical service lines
escrow activity tables
```

- [ ] Add table consistency gate:
  - [ ] If Docling is authoritative for row source, Granite may label/map rows but may not create ungrounded rows.
  - [ ] Any Granite row without a Docling `row_index` is rejected or converted to review-only observation.
  - [ ] If extracted row count differs materially from Docling candidate row count, mark extraction review-required and record `candidate.table_row_count_mismatch`.
- [ ] Preserve table provenance into the envelope:

```text
table_id
row_index
page_number
semantic_region_id
```

- [ ] Tests:
  - [ ] Strong table routes to `docling_table_plus_granite_labeler`.
  - [ ] Weak table routes conservatively.
  - [ ] Continuation risk routes conservatively.
  - [ ] Row index/table ID/page evidence survives normalization.
  - [ ] Granite cannot invent rows when Docling row source is authoritative.
  - [ ] Row-count mismatch records review-required status and taxonomy code.

## Task 11: Keep Visual Input Planning Conservative

- [ ] Preserve `lib/extraction/visual_input_planning.py` default behavior as `shadow_full_page`.
- [ ] Use planned crops only when all are true:

```text
geometry basis is reliable
rotation/skew risk is acceptable
crop quality is acceptable
bbox is not ambiguous
continuation risk is low
output usefulness is expected to improve
```

- [ ] Fall back to full page when any are true:

```text
skew/rotation risk
ambiguous bbox basis
missing table bbox
low resolution
continuation risk
semantic region spans page boundaries
```

- [ ] Persist visual-plan decision and retry outcome in `ExtractionPlanTask.visual_plan_summary`.
- [ ] Tests:
  - [ ] Risky crop plans remain shadow-only.
  - [ ] Missing/ambiguous geometry falls back to full page.
  - [ ] Visual plan decision is visible in persisted plan tasks and corpus report.

## Task 12: Add Run Manifests, Reports, And Repeatability

- [ ] Add run manifest fields to `scripts/run_model_corpus.py` and the GPU resident wrapper:

```json
{
  "run_id": "phase85-YYYYMMDD-smoke-NNN",
  "pipeline_version": "phase8_5_reliability_v1",
  "docling_version": "...",
  "semantic_profile": "qwen3-vl-8b-fp8-semantic:v1",
  "semantic_prompt_version": "phase8_5-semantic-smart-v3",
  "granite_model": "ibm-granite/granite-4.0-3b-vision",
  "granite_prompt_version": "phase8_5-granite-structured-v1",
  "planner_version": "phase8_5-closed-world-planner-v1",
  "contract_registry_version": "phase8_5-contract-registry-v1",
  "region_envelope_version": "phase8_5-region-envelope-v1",
  "candidate_gate_version": "phase8_5-candidate-gates-v1",
  "reconciler_version": "phase8_5-reconciler-v1",
  "visual_input_plan_version": "phase8_5-visual-plan-v1",
  "decoding": {
    "temperature": 0,
    "top_p": null
  }
}
```

- [ ] Report these summaries:

```text
planner selected/skipped/abstained counts
missing contract/grounding/schema counts
contract resolution modes
envelope facts/line_items/table_rows/observations counts
admitted/rejected candidate counts
candidate rejection reason distribution
concrete evidence coverage
visual input plan route distribution
retry outcomes
duplicate suppression counts
extraction pressure metrics
safe abstention/skip/rejection counts
quality status and review requirement
```

- [ ] Include extraction-pressure metrics:

```text
planned_task_count
selected_task_count
selected_task_count_by_backend
selected_task_count_by_page
max_tasks_per_document_policy
max_tasks_per_page_policy
budget_exceeded_count
estimated_visual_tokens
estimated_docling_context_tokens
```

- [ ] Include safe-outcome categories:

```text
safe_abstention_count
safe_skip_count
safe_rejection_count
unsafe_failure_count
```

- [ ] Add repeatability fingerprints for:

```text
document family
semantic regions
planner tasks
candidate fingerprints
canonical output
review tasks
rejection distribution
```

- [ ] Tests:
  - [ ] Corpus report includes the run manifest.
  - [ ] Admission events link to run ID and gate versions.
  - [ ] Planner summaries link to run ID and planner version.
  - [ ] Repeated deterministic fixture run produces stable planner and candidate fingerprints.

## Task 13: Define Truth, Review, Debug, And Phase 9 Eligibility

- [ ] Document and enforce surfaces:

```text
Truth:
  accepted canonical fields
  accepted canonical line items
  accepted canonical observations
  user-confirmed facts

Review:
  review-required field candidates
  review-required line-item candidates
  review-required observation candidates
  candidate rejection summaries
  uncertain observations
  evidence refs
  planner explanations
  quality signals

Debug:
  raw model output
  prompt versions
  visual plan internals
  region envelope
  normalization repairs
  model-output payloads
  adapter traces
```

- [ ] Default product UI and Phase 9 context may consume truth surfaces directly.
- [ ] Review surfaces require uncertainty labels.
- [ ] Debug surfaces are not truth and must not be standalone factual context for Phase 9.
- [ ] Add or plan a Phase 9 document eligibility helper:

```python
def phase9_document_eligibility(document_quality: dict) -> str:
    if document_quality["operational_status"] != "completed":
        return "analysis_disabled_operational_failure"

    if document_quality["canonical_fact_count"] == 0 and document_quality["candidate_count"] == 0:
        return "analysis_limited_no_extracted_facts"

    if document_quality["evidence_locator_coverage"] < 0.80:
        return "analysis_review_only_evidence_sparse"

    if document_quality["has_admitted_artifact"]:
        return "analysis_disabled_artifact_regression"

    return "analysis_enabled_with_uncertainty"
```

- [ ] Tests:
  - [ ] Review-required candidates are labeled as uncertain in any Phase 9 intake model.
  - [ ] Raw model output and debug envelopes are excluded from truth context.
  - [ ] Document-level eligibility returns the correct disabled/limited/review-only/enabled state.
  - [ ] Phase 9 output cannot mutate canonical facts, relationships, folders, tags, deadlines, or review status without explicit user action.

## Task 14: Acceptance Gates

Hard correctness invariants, zero every smoke/resident run:

- [ ] Selected/enqueued Granite semantic-region tasks missing `model_output_schema_name`.
- [ ] Selected/enqueued Granite semantic-region tasks missing concrete grounding.
- [ ] Selected/enqueued incompatible family/schema Granite tasks.
- [ ] Prompt/schema artifacts admitted.
- [ ] Placeholder or literal-null candidates admitted.
- [ ] Candidates admitted without concrete evidence.
- [ ] Model-backed semantic-region rows marked `auto_accepted`.
- [ ] Fabricated canonical required fields.
- [ ] Document-title-derived merchant/seller unless explicitly allowlisted.
- [ ] Aggregate schemas created from incompatible source families.

Operational SLOs:

- [ ] Smoke/resident corpus: `0` target queue dead letters.
- [ ] Shadow/production corpus: dead-letter rate below threshold, all dead letters classified, jobs retry-safe, and no candidate/canonical corruption from failed jobs.
- [ ] Retry success rate above the defined threshold.
- [ ] Docling, semantic, and extraction runtime failure rates below defined thresholds.
- [ ] No runaway fanout.
- [ ] Every operational failure has a taxonomy code.
- [ ] Jobs remain idempotent and retry-safe.

Gold-corpus quality metrics:

- [ ] Family top-1 and top-2 accuracy.
- [ ] Field precision/recall/F1 by family.
- [ ] Line-item row precision/recall/F1 by family.
- [ ] Amount/date normalization accuracy.
- [ ] Evidence locator completeness.
- [ ] Duplicate rate.
- [ ] Review burden.
- [ ] False canonical promotion rate.
- [ ] Repeatability stability.
- [ ] Confidence calibration by family/field.
- [ ] Expected calibration error.
- [ ] Precision at confidence buckets.
- [ ] Review burden at confidence thresholds.

## Task 15: Definition Of Done For Phase 8.5 Reliability

Phase 8.5 reliability is done when:

- [ ] The smoke/resident corpus passes all hard correctness invariants twice with stable planner and candidate fingerprints.
- [ ] The resident run report exposes planner, contract, evidence, envelope, admission, dedupe, and visual-plan summaries.
- [ ] No selected/enqueued Granite task lacks a model-output contract or concrete grounding.
- [ ] No rejected candidate is inserted.
- [ ] No model-backed semantic-region extraction is `auto_accepted`.
- [ ] All Phase 9 input surfaces distinguish truth, review, and debug material.
- [ ] The first gold-corpus baseline report exists, including calibration metrics, even if quality thresholds are not sufficient for auto-promotion.
- [ ] Granite replacement/bakeoff remains deferred or is run only through the same stabilized control plane.

## Verification Commands

Run focused local checks after implementation:

```bash
ruff check .
ruff format --check .
python scripts/validate_contracts.py
pytest tests/unit/semantic_annotations/test_extraction_plan.py \
  tests/unit/semantic_annotations/test_extraction_plan_repository.py \
  tests/unit/extraction/test_contract_registry.py \
  tests/unit/extraction/test_region_envelope.py \
  tests/unit/extraction/test_evidence_concretizer.py \
  tests/unit/extraction/test_candidate_admission.py \
  tests/unit/extraction/test_model_output_normalization.py \
  tests/unit/extraction/test_docling_table_quality.py \
  tests/unit/extraction/test_reconciliation.py \
  tests/unit/scripts/test_model_corpus_report.py
pyright
mypy .
```

Run the resident GPU validation before claiming the Phase 8.5 reliability gate:

```bash
python scripts/run_model_corpus.py --mode resident --emit-run-manifest --repeatability-pass 1
python scripts/run_model_corpus.py --mode resident --emit-run-manifest --repeatability-pass 2
```

Use the project's current GPU wrapper if it supersedes the direct command above. The acceptance evidence must show hard invariants, planner/admission summaries, and stable fingerprints.
