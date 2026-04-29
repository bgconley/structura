# Phase 8.5 Qwen3-VL-4B Smart Parse And Canary Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the default Smart Parse Qwen3-VL-2B semantic service with Qwen3-VL-4B, disable active Qwen3-VL-8B HQ/rescue runtime paths, and harden Granite routing/normalization/aggregation so the expanded private corpus produces durable candidates or reviewable observations without regressions.

**Architecture:** Keep the existing Docling -> Qwen semantic manifest -> Granite targeted extraction -> validators/review pipeline. Preserve existing semantic contracts, update runtime profile identity and routing vocabulary additively, validate Granite output against small model-output contracts, map into canonical candidates or reviewable observations, and build aggregates only from supported evidence.

**Tech Stack:** Python services/repositories, PostgreSQL migrations, JSON Schema contracts, vLLM OpenAI-compatible vision adapters, Docker Compose model services, FastAPI routes, React Viewer controls, pytest, Playwright, GPU private-corpus validation.

---

## Scope

This plan implements the spec in
`docs/superpowers/specs/2026-04-29-phase-8-5-qwen3-vl-4b-smart-parse-canary-spec.md`.

It must not start Phase 9, introduce ColQwen, delete historical Qwen2B/Qwen8
contracts, or make Granite output canonical app JSON directly.

## Implementation Notes From Code Seam Review

- `model-qwen-semantic:8104` should stay the smart service name/port so app
  wiring remains stable.
- `model-qwen` should leave the active `models-live` runtime path while Qwen8 is
  deferred. Keep the contract surface and historical provenance support.
- `workers/model_services/start_qwen_vllm.sh` already accepts the Qwen3-VL-4B runtime
  knobs needed for this pass.
- `lib/semantic_annotations/qwen_gateway.py` currently assumes smart, high
  quality, and rescue modes are runnable. It needs explicit disabled behavior
  for HQ/rescue, not a remap to Qwen3-VL-4B.
- `semantic_annotation_manifest.v1` and
  `semantic_annotation_model_output.v1` already exist. Expand enums additively.
- `lib/extraction/model_output_schemas.py` and
  `lib/extraction/granite_prompting.py` are the right place to add Granite
  schema/task routing.
- `lib/extraction/model_output_normalization.py` is the right place for
  defensive arbitrary-JSON repair/mapping.
- `lib/extraction/reconciliation_repository.py` currently waits for all expected
  region jobs to succeed before aggregate creation. It must distinguish terminal
  runtime failures from usable sibling outputs.
- `lib/extraction/extraction_repository.py` is already large. Add observation
  persistence through a focused repository/module rather than turning it into a
  larger catch-all.

## Task 1: Lock In Regression Tests First

**Files:**
- Modify: `tests/unit/model_runtime/test_profiles.py`
- Modify: `tests/unit/test_compose_model_profiles.py`
- Modify: `tests/unit/semantic_annotations/test_gateways.py`
- Modify: `tests/unit/semantic_annotations/test_jobs.py`
- Modify: `tests/unit/semantic_annotations/test_service.py`
- Modify: `tests/unit/extraction/test_model_output_normalization.py`
- Modify: `tests/unit/extraction/test_semantic_region_routing.py`
- Modify: `tests/unit/extraction/test_reconciliation.py`
- Modify: `tests/unit/test_phase8_5_private_corpus_runner.py`
- Modify: `tests/e2e/phase8.spec.ts`

- [ ] Add tests proving the smart semantic profile is `qwen3-vl-4b-semantic:v1`
      with source engine `qwen3_vl_4b`.
- [ ] Add tests proving `model-qwen-semantic` uses `Qwen/Qwen3-VL-4B-Instruct`,
      max model length 16384, max sequences 2, video cap 0, and bounded image
      fan-in.
- [ ] Add tests proving `model-qwen` is not part of the active `models-live`
      path while Qwen8 is deferred.
- [ ] Add API/job/service tests proving High Quality Parse and Allow 8B Rescue
      are explicit but disabled/deferred, and are not silently remapped to
      Qwen3-VL-4B.
- [ ] Add semantic contract tests for the expanded document-family and
      semantic-region vocabulary.
- [ ] Add Granite routing tests for receipt/order tables, title seller-info,
      mortgage escrow, dispute form, generic form KVP, and no-target regions.
- [ ] Add normalization tests for dict/list/string/null/schema echo/wrapped
      data/flat receipt fields/retail order rows.
- [ ] Add reconciliation tests proving payment summary cannot erase line items,
      unsupported documents do not become invoice/EOB aggregates, and partial
      region runtime failure preserves successful sibling regions.
- [ ] Add private corpus runner tests proving default canary runs Smart Parse
      only, Qwen8 call count must be zero, and private paths are not committed.

Run targeted tests and confirm they fail for missing behavior before
implementation.

## Task 2: Swap Smart Semantic Runtime To Qwen3-VL-4B

**Files:**
- Modify: `lib/model_runtime/profiles.py`
- Modify: `lib/config/settings.py`
- Modify: `compose.yaml`
- Modify: `workers/model_services/start_qwen_vllm.sh` only if launch flags need
  safe fallback handling
- Modify: `scripts/gpu/phase8_5_model_smoke.sh`
- Modify: `tests/unit/model_runtime/test_profiles.py`
- Modify: `tests/unit/test_compose_model_profiles.py`

- [ ] Add `QWEN_SEMANTIC_PROFILE = "qwen3-vl-4b-semantic:v1"`.
- [ ] Preserve historical profile constants/metadata needed to read Qwen2B and
      Qwen8 provenance.
- [ ] Set Qwen3-VL-4B base model to `Qwen/Qwen3-VL-4B-Instruct` and source engine to
      `qwen3_vl_4b`.
- [ ] Set smart default max model length to 16384, max images initially to 1,
      and video to 0 so the existing page-window merge path preserves exact
      Docling page coverage.
- [ ] Set Compose `model-qwen-semantic` to Qwen3-VL-4B BF16, max sequences 2, and
      conservative GPU memory utilization.
- [ ] Probe `STRUCTURA_VLLM_KV_CACHE_DTYPE=fp8` only behind a setting that can
      be removed without code changes if vLLM rejects it.
- [ ] Remove `model-qwen` from active `models-live` startup and smoke gates
      while keeping a future/evaluation profile available if useful.
- [ ] Update model runtime required-live profile tests so Qwen8 is not required
      for the default Phase 8.5 gate.

## Task 3: Disable HQ/Rescue Without Breaking Contracts

**Files:**
- Modify: `lib/semantic_annotations/qwen_gateway.py`
- Modify: `lib/semantic_annotations/jobs.py`
- Modify: `lib/semantic_annotations/service.py`
- Modify: `apps/api/structura_api/routes_documents.py`
- Modify: `contracts/api/openapi.yaml`
- Modify: `apps/web/src/components/Viewer.tsx`
- Modify: `tests/unit/semantic_annotations/test_jobs.py`
- Modify: `tests/unit/semantic_annotations/test_service.py`
- Modify: `tests/e2e/phase8.spec.ts`

- [ ] Add a setting or capability flag that marks Qwen8 HQ/rescue disabled.
- [ ] Reject or no-op HQ/rescue enqueue attempts with an explicit
      disabled/deferred state and audit-visible reason.
- [ ] Keep `semantic_quality_mode`, `allow_8b_rescue`, `requested_by_user_id`,
      and `user_intent_reason` fields intact for future re-enable.
- [ ] Ensure existing `rescue_policy` cannot enqueue rescue without an enabled
      Qwen8 capability and explicit user permission.
- [ ] Update Viewer controls so the user cannot accidentally start HQ/rescue
      while the runtime is disabled.
- [ ] Update OpenAPI/tests to show the preserved endpoint contract plus current
      disabled response.

## Task 4: Expand Semantic Vocabulary Additively

**Files:**
- Modify: `contracts/schemas/semantic_annotation_manifest.v1.schema.json`
- Modify: `contracts/schemas/semantic_annotation_model_output.v1.schema.json`
- Modify: `lib/semantic_annotations/policy.py`
- Modify: `lib/semantic_annotations/qwen_output_normalization.py`
- Modify: `lib/semantic_annotations/qwen_gateway.py`
- Add migration if database constraints need new enum values
- Modify semantic annotation unit tests

- [ ] Add expanded document-family enums for retail order, title, escrow,
      dispute form, travel/restaurant receipts, generic form, unsupported, and
      no-target documents.
- [ ] Add expanded semantic-region enums for retail/order line tables,
      seller-info, escrow, dispute, generic KVP, unsupported, and no-target
      regions.
- [ ] Add target-schema or observation-target values only where downstream
      mapping exists.
- [ ] Update Qwen prompt wording so unfamiliar documents route to generic
      observations or unsupported/no-target states instead of forced invoice,
      receipt, or EOB families.
- [ ] Preserve `needs_high_quality_pass` only as a diagnostic/review signal
      while Qwen8 is disabled; it must not trigger HQ/rescue automatically.
- [ ] Keep structured-output schema shape vLLM-friendly and bounded.

## Task 5: Harden Granite Structured Output And Telemetry

**Files:**
- Modify: `lib/model_runtime/contracts.py`
- Modify: `lib/model_runtime/clients/_openai_vision.py`
- Modify: `lib/model_runtime/clients/granite.py`
- Modify: `lib/extraction/gateways/_vision.py`
- Modify: tests under `tests/unit/model_runtime/` and
  `tests/unit/extraction/`

- [ ] Add response telemetry fields for finish reason, usage JSON, output token
      count when available, structured-output mode, and fallback reason.
- [ ] Add a capability-probe or controlled fallback path for
      `response_format: json_schema`.
- [ ] Keep prompt-level schema instructions even when structured output is
      enabled.
- [ ] Record semantic type, model-output schema, prompt/input estimate, finish
      reason, timeout/retry reason, raw response pointer, and normalization
      result in raw output and/or `normalization_json`.
- [ ] Treat Granite timeout or adapter exception as a region `pipeline_failed`
      runtime outcome while preserving successful sibling regions.

## Task 6: Add Granite Model-Output Schemas And Routing

**Files:**
- Create: `contracts/model_outputs/granite_receipt_line_items.v1.schema.json`
- Create: `contracts/model_outputs/granite_receipt_payment_summary.v1.schema.json`
- Create: `contracts/model_outputs/granite_retail_order.v1.schema.json`
- Create: `contracts/model_outputs/granite_real_estate_title_seller_info.v1.schema.json`
- Create: `contracts/model_outputs/granite_mortgage_escrow_statement.v1.schema.json`
- Create: `contracts/model_outputs/granite_dispute_form.v1.schema.json`
- Create: `contracts/model_outputs/granite_generic_kvp.v1.schema.json`
- Modify: `lib/extraction/model_output_schemas.py`
- Modify: `lib/extraction/granite_prompting.py`
- Modify: `tests/unit/extraction/test_semantic_region_routing.py`

- [ ] Route table semantic types to `<tables_json>` with Docling table context
      and page/crop image input.
- [ ] Route KVP semantic types to schema-based Granite KVP prompts.
- [ ] Route unknown useful form regions to `granite_generic_kvp.v1`.
- [ ] Route low-signal/blank/boilerplate regions to
      `insufficient_signal`/`no_extraction_target`.
- [ ] Prefer semantic type and Granite task over broad document family when
      selecting model-output schema.
- [ ] Keep each schema shallow and bounded for vLLM structured-output
      reliability.

## Task 7: Add Reviewable Observation Persistence

**Files:**
- Create: `database/079_phase8_5_extraction_observations.sql`
- Create: `lib/extraction/observation_repository.py`
- Modify: `lib/extraction/models.py`
- Modify: `lib/extraction/extraction_repository.py` minimally
- Modify: `lib/documents/read_model.py` or add focused read-model helper if
  observation display/query support needs it
- Modify: `tests/unit/test_migrations.py`
- Add extraction observation tests

- [ ] Add an `extraction_observations` table or equivalent candidate family
      with extraction, semantic annotation, semantic region, schema, field,
      value, confidence, review status, evidence, and normalization metadata.
- [ ] Preserve region provenance through `document_extractions` plus
      observation evidence JSON.
- [ ] Keep invoice/receipt/EOB line-item tables as-is unless profiling proves a
      join bottleneck.
- [ ] Add repository methods in a focused observation module; avoid adding broad
      domain behavior to `extraction_repository.py`.
- [ ] Make observations queryable for review/debug/read-model use without
      promoting them to canonical facts.

## Task 8: Make Normalization Non-Fragile

**Files:**
- Modify: `lib/extraction/model_output_normalization.py`
- Modify: `lib/extraction/normalization.py`
- Modify: `lib/extraction/service.py` only where orchestration needs
  normalization metadata
- Modify: `tests/unit/extraction/test_model_output_normalization.py`

- [ ] Change Granite normalization entry points to accept `object`, not only
      `dict[str, Any]`.
- [ ] Safely handle wrappers such as `normalized`, `data`, schema echo, array
      roots, string roots, null roots, and flat field payloads.
- [ ] Map receipt/order line items and payment summaries into canonical
      candidates where evidence supports it.
- [ ] Map title/escrow/dispute/generic fields into observations.
- [ ] Record repairs, rejected fields, unsupported fields, and confidence/evidence
      gaps in `normalization_json`.
- [ ] Return reviewable output rather than raising when the model produced
      useful but unmapped content.

## Task 9: Tighten Aggregation And Partial-Failure Handling

**Files:**
- Modify: `lib/extraction/reconciliation.py`
- Modify: `lib/extraction/reconciliation_repository.py`
- Modify: `lib/extraction/validators.py` if aggregate review metadata needs it
- Modify: reconciliation tests

- [ ] Aggregate invoice only when invoice evidence or invoice model-output
      schemas support it.
- [ ] Add receipt/order aggregate support only where evidence supports it.
- [ ] Do not aggregate title/escrow/dispute/generic observations into invoice or
      EOB schemas.
- [ ] Preserve service and line candidates when payment-summary regions finish
      later.
- [ ] Treat all terminal region jobs as aggregate input state, not only all
      succeeded jobs.
- [ ] Include failed/missing region diagnostics in aggregate review metadata
      without discarding successful sibling outputs.
- [ ] Preserve extraction ID and semantic region ID in aggregate evidence refs.

## Task 10: Turn The Real PDFs Into A Private Canary Gate

**Files:**
- Modify: `scripts/gpu/run_phase8_5_private_corpus.py`
- Create: `contracts/private_corpus/phase8_5_canary_manifest.schema.json` or a
  committed template under `tests/fixtures/model_corpus/`
- Modify: `.gitignore` if needed to keep `.runtime/private-corpus/*.local.json`
  private
- Modify: `tests/unit/test_phase8_5_private_corpus_runner.py`

- [ ] Add `--manifest <path>` support for private canary expectations.
- [ ] Commit a manifest schema/template, not private document paths.
- [ ] Define invariants for the nine-document probe plus BMW and Anthem docs.
- [ ] Report Qwen8 call count, semantic profile, document family, target
      schemas, region scopes, line-item counts, observation counts, aggregate
      rows, failed runtime jobs, review outcomes, and provenance.
- [ ] Make default canary mode Smart Parse only. Disable or reject
      `--high-quality`, `--allow-8b-rescue`, and `--rescue-stress` while Qwen8
      is deferred unless an explicit future evaluation profile re-enables them.
- [ ] Ensure partial Granite runtime failures appear in the report without
      hiding successful sibling region output.

## Task 11: Local Verification

Run after implementation:

```bash
python -m pytest -q tests/unit/model_runtime/test_profiles.py tests/unit/test_compose_model_profiles.py
python -m pytest -q tests/unit/semantic_annotations
python -m pytest -q tests/unit/extraction
python -m pytest -q tests/unit/test_phase8_5_private_corpus_runner.py tests/unit/test_migrations.py
python -m ruff check .
python -m ruff format --check .
make contracts
```

Run broader checks expected for Phase 8.5 work:

```bash
python -m pytest
python -m mypy .
python -m pyright
make sast
```

Adjust the exact commands only if the repository's current make targets or test
layout require it. Record any skipped GPU-only checks explicitly.

## Task 12: GPU Validation Gate

Run on the GPU node after commit/push/pull:

```bash
cd /tank/repos/structura
git pull --ff-only origin master
docker compose --profile models-live up -d --force-recreate model-qwen-semantic model-granite
STRUCTURA_MODEL_SMOKE_MANAGE_COMPOSE=1 scripts/gpu/phase8_5_model_smoke.sh
STRUCTURA_MODEL_MODE=live python scripts/gpu/run_phase8_5_private_corpus.py --manifest .runtime/private-corpus/phase8_5_canary_manifest.local.json
```

Required proof:

- [ ] Qwen smart profile is `qwen3-vl-4b-semantic:v1`.
- [ ] Qwen8 call count is zero.
- [ ] BMW service line candidates survive payment-summary extraction.
- [ ] Anthem denial/EOB routes to medical/EOB candidates or reviewable medical
      observations.
- [ ] BH Photo produces retail order/receipt candidates or observations.
- [ ] Phenix Title and UWM escrow do not masquerade as invoice/EOB.
- [ ] Generic scans become useful observations, `insufficient_signal`, or
      `no_extraction_target`; they do not fabricate invoice/EOB data.
- [ ] Partial Granite runtime failure preserves successful sibling outputs.
- [ ] Model provenance matches actual adapter invocation.
- [ ] Aggregate document read models return what the app expects.

## Task 13: Documentation And Handoff

**Files:**
- Modify: `AGENTS.md` if durable guidance changes after implementation.
- Modify: `.wolf/cerebrum.md` and `.wolf/memory.md` only if the user asks to
  update OpenWolf notes after implementation.
- Modify: `STRUCTURA_PHASE_8_5_IMPLEMENTATION_PLAN.md` only if this plan becomes
  the active canonical Phase 8.5 sequence.

- [ ] Document the Qwen3-VL-4B Smart Parse runtime profile and Qwen8 disabled/deferred
      state.
- [ ] Document the private canary gate and non-committed manifest path.
- [ ] Record any measured GPU profile changes, such as image fan-in, KV dtype,
      or max sequence count.
- [ ] Commit and push only after local checks and user-requested GPU gates are
      complete.
