# Phase 8.5 Critical Extraction Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve useful Granite region outputs, convert them into reviewable canonical candidates, and produce aggregate document extractions without automatic Qwen8B escalation.

**Architecture:** Semantic-region Granite outputs are persisted as scoped extraction runs, validated against small model-output contracts, normalized into candidate facts, and later reconciled into an aggregate document extraction. Canonical app schemas remain owned by Structura; Granite emits model-output schemas or table task JSON that Structura maps and audits.

**Tech Stack:** Python services/repositories, PostgreSQL migrations, JSON Schema contracts, vLLM OpenAI-compatible Granite adapter, pytest.

---

### Task 1: Regression Tests

**Files:**
- Modify: `tests/unit/extraction/test_extraction_persistence_policy.py`
- Modify: `tests/unit/extraction/test_semantic_region_routing.py`
- Modify: `tests/unit/extraction/test_model_gateways.py`
- Modify: `tests/unit/test_migrations.py`

- [x] Add tests proving two current invoice region extractions do not supersede each other.
- [x] Add tests proving BMW-style flat service fields produce invoice line item candidates.
- [x] Add tests proving payment-summary extraction cannot erase service-line candidates.
- [x] Add tests proving Phase 8.5 migration adds scoped extraction columns/indexes.
- [x] Run targeted tests and confirm they fail for missing behavior.

### Task 2: Scoped Extraction Persistence

**Files:**
- Create: `database/078_phase8_5_region_extraction_scope.sql`
- Modify: `lib/extraction/models.py`
- Modify: `lib/extraction/extraction_repository.py`
- Modify: `lib/extraction/service.py`
- Modify: `lib/documents/read_model.py`

- [x] Add `extraction_scope`, `semantic_annotation_id`, `source_semantic_region_id`, `semantic_type`, `granite_task`, `model_output_schema_name`, `model_output_schema_version`, `normalization_json`, and `metadata_json` to `document_extractions`.
- [x] Replace the global current index with document-level and semantic-region-level current indexes.
- [x] Persist semantic task metadata into extraction rows.
- [x] Supersede only matching document-level or matching region-level rows.
- [x] Prefer aggregate/document rows in document detail summaries while preserving region rows for review/debug queries.

### Task 3: Model-Output Contracts And Granite Routing

**Files:**
- Create: `contracts/model_outputs/granite_invoice_line_items.v1.schema.json`
- Create: `contracts/model_outputs/granite_payment_summary.v1.schema.json`
- Create: `contracts/model_outputs/granite_medical_service_lines.v1.schema.json`
- Create: `lib/extraction/model_output_schemas.py`
- Create: `lib/extraction/granite_prompting.py`
- Modify: `lib/extraction/gateways/_vision.py`
- Modify: `lib/model_runtime/clients/granite.py` if schema forwarding requires adapter support

- [x] Add small model-output schemas for table line items, payment summaries, and EOB service lines.
- [x] Select model-output schema and prompt by `semantic_type`/`granite_task`.
- [x] Use `<tables_json>` for table extraction tasks and VAREX-style JSON Schema prompts for KVP tasks.
- [x] Pass `response_json_schema` when supported by the existing model-runtime request path; tolerate unsupported structured-output failures via normal validation/review flow.

### Task 4: Normalization And Candidate Mapping

**Files:**
- Create: `lib/extraction/model_output_normalization.py`
- Modify: `lib/extraction/normalization.py`
- Modify: `lib/extraction/validators.py` only if canonical validation needs model-output-aware review metadata
- Modify: `lib/extraction/extraction_repository.py`

- [x] Map `granite_invoice_line_items.v1` and BMW-style flat arrays into canonical invoice line-item candidates.
- [x] Preserve raw model output and record repairs/rejected fields in `normalization_json`.
- [x] Mark repaired/noncanonical model output as `needs_review`; never promote without validators/review policy.
- [x] Keep validation mismatch as document-quality review state, not worker failure.

### Task 5: Region Reconciliation

**Files:**
- Create: `lib/extraction/reconciliation.py`
- Modify: `lib/semantic_annotations/service.py` or extraction worker seam that can observe terminal region jobs
- Add tests under `tests/unit/extraction/`

- [x] Build aggregate invoice payloads from current region outputs for one semantic annotation.
- [x] Merge service/line item regions with summary/payment regions without deleting either.
- [x] Preserve extraction ID and semantic region provenance in evidence/metadata.
- [x] Keep aggregate rows document-scoped and separately current from region rows.

### Task 6: Verification

**Files:**
- Modify only as required by test failures.

- [ ] Run ruff, format check, mypy/pyright scope, contract validation, and targeted pytest locally/GPU as appropriate.
- [ ] Push, pull on GPU node, rebuild affected workers/services.
- [ ] Run the two real PDFs through the full live pipeline.
- [ ] Prove BMW service line candidates are present, payment summary remains present, no Qwen8B was invoked, no failed jobs exist, and aggregate extraction is retrievable.
