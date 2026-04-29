# Phase 8.5 Qwen Visual Token Budget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bound Qwen3-VL-4B Smart Parse image tokenization, preserve four-page semantic fan-in, and add token-budget canary evidence before corpus reruns.

**Architecture:** Keep Qwen-specific serving behavior in the vLLM start wrapper and Compose service definition. Keep planner budget metadata in the model profile registry so scripts and tests can inspect the contract. Keep token accounting inside the GPU semantic canary harness; it reports diagnostics without changing live extraction or Granite inputs.

**Tech Stack:** Python 3.11, pytest, Docker Compose, vLLM OpenAI server, Qwen3-VL-4B, Structura Phase 8.5 model-runtime contracts.

---

## File Structure

- `lib/model_runtime/profiles.py`: add Qwen semantic visual-token budget metadata.
- `workers/model_services/start_qwen_vllm.sh`: forward `STRUCTURA_VLLM_MM_PROCESSOR_KWARGS` to vLLM.
- `compose.yaml`: set Qwen semantic `STRUCTURA_VLLM_MM_PROCESSOR_KWARGS` to the 2560-token/page planner budget.
- `workers/model_services/qwen-vllm.example.env`: keep the operator example aligned with Qwen3-VL-4B Smart Parse.
- `scripts/gpu/run_phase8_5_semantic_canary.py`: emit token-budget diagnostics.
- `lib/semantic_annotations/docling_context.py`: allow Qwen prompts to omit
  token-heavy bboxes and page image hashes while preserving default full Docling
  context for other callers.
- `STRUCTURA_PHASE_8_5_IMPLEMENTATION_PLAN.md`: record the 4B planner-resolution budget.
- `STRUCTURA_PHASE_8_5_SEMANTIC_ANNOTATION_PLAN.md`: remove the stale one-image-default statement and record the adaptive four-image policy.
- `docs/superpowers/specs/2026-04-29-phase-8-5-qwen-visual-token-budget-spec.md`: focused spec for this work.
- Tests:
  - `tests/unit/model_runtime/test_profiles.py`
  - `tests/unit/test_compose_model_profiles.py`
  - `tests/unit/test_config.py`
  - `tests/unit/test_model_service_scripts.py`
  - `tests/unit/scripts/test_phase8_5_semantic_canary.py`
  - `tests/unit/semantic_annotations/test_gateways.py`

## Task 1: Preserve The Timeout Patch

- [ ] Keep `model_qwen_semantic_timeout_seconds = 300`.
- [ ] Keep `model_qwen_hq_timeout_seconds = 180`.
- [ ] Keep `_timeout_seconds_for_profile()` reading those settings.
- [ ] Verify:

```bash
.venv/bin/python -m pytest tests/unit/test_config.py tests/unit/semantic_annotations/test_gateways.py::test_live_qwen_smart_gateway_builds_truthful_qwen3_vl_4b_manifest -q
```

## Task 2: Add vLLM Processor Kwargs

- [ ] Add failing assertions that the Qwen start script forwards `STRUCTURA_VLLM_MM_PROCESSOR_KWARGS`.
- [ ] Add failing Compose assertions for:

```text
STRUCTURA_VLLM_MM_PROCESSOR_KWARGS={"size":{"shortest_edge":262144,"longest_edge":2621440}}
```

- [ ] Implement shell forwarding:

```bash
if [[ -n "${STRUCTURA_VLLM_MM_PROCESSOR_KWARGS:-}" ]]; then
  args+=(--mm-processor-kwargs "$STRUCTURA_VLLM_MM_PROCESSOR_KWARGS")
fi
```

- [ ] Verify:

```bash
.venv/bin/python -m pytest tests/unit/test_model_service_scripts.py tests/unit/test_compose_model_profiles.py -q
```

## Task 3: Add Profile Budget Metadata

- [ ] Add fields to `ModelProfile`:

```python
visual_token_spatial_compression: int | None = None
visual_token_min_per_image: int | None = None
visual_token_max_per_image: int | None = None
```

- [ ] Set the Qwen semantic profile to `32`, `256`, and `2560`.
- [ ] Verify:

```bash
.venv/bin/python -m pytest tests/unit/model_runtime/test_profiles.py -q
```

## Task 4: Add Canary Token-Budget Report

- [ ] Add tests proving the canary reports page dimensions, estimated grid, visual tokens, prompt/context/schema estimates, output tokens, conservative total, and fan-in.
- [ ] Implement standard-library PNG/JPEG dimension parsing so the script does not add Pillow to the shared runtime.
- [ ] Estimate text/schema tokens with a conservative `ceil(characters / 4)` heuristic.
- [ ] Estimate Qwen visual tokens using the profile budget and 32x compression.
- [ ] Report whether Qwen prompt context contains legacy page aliases, element
      bboxes, or page image hashes.
- [ ] Verify:

```bash
.venv/bin/python -m pytest tests/unit/scripts/test_phase8_5_semantic_canary.py -q
```

## Task 5: Align Phase Docs

- [ ] Update the Phase 8.5 implementation and semantic annotation plans with the planner-resolution image budget, four-image first attempt, fallback behavior, and canary evidence requirement.
- [ ] Verify no stale one-image Smart Parse statement remains:

```bash
rg -n "one image per request by default|bounded to one image" STRUCTURA_PHASE_8_5_*.md docs/superpowers/specs docs/superpowers/plans
```

## Task 6: Focused Local Verification

- [ ] Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_config.py \
  tests/unit/model_runtime/test_profiles.py \
  tests/unit/test_compose_model_profiles.py \
  tests/unit/test_model_service_scripts.py \
  tests/unit/scripts/test_phase8_5_semantic_canary.py \
  tests/unit/semantic_annotations/test_gateways.py::test_live_qwen_smart_gateway_builds_truthful_qwen3_vl_4b_manifest \
  -q
```

- [ ] Run formatter/lint checks on touched Python files if available:

```bash
.venv/bin/python -m ruff check lib/model_runtime/profiles.py scripts/gpu/run_phase8_5_semantic_canary.py tests/unit/scripts/test_phase8_5_semantic_canary.py tests/unit/model_runtime/test_profiles.py tests/unit/test_compose_model_profiles.py tests/unit/test_model_service_scripts.py tests/unit/test_config.py tests/unit/semantic_annotations/test_gateways.py
```

## Task 7: GPU Canary Handoff

- [ ] Push/pull to the GPU node only when the user asks for commit/push, or run from the current checkout if already synced.
- [ ] Restart `model-qwen-semantic` with the staged service profile.
- [ ] Run BH Photo, BMW, and EOB first.
- [ ] Run the nine-document canary after those are stable.
- [ ] Confirm the report records selected fan-in, page dimensions, visual tokens, requested output tokens, and no Qwen3-VL 8B calls.
