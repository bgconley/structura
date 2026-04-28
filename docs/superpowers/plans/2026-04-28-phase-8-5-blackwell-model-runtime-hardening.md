# Phase 8.5 Blackwell Model Runtime Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Phase 8.5 live model serving deterministic on the 2x RTX PRO 4000 Blackwell GPU node by using source-backed vLLM/Compose configuration, real readiness waits, and inference probes.

**Architecture:** Docker Compose owns physical GPU placement with explicit device reservations; each container sees exactly one GPU and uses inside-container `CUDA_VISIBLE_DEVICES=0`. Model launch scripts expose memory/context/concurrency knobs without hardcoding oversized defaults, and the GPU smoke waits for first-load readiness before forcing inference probes. Live GPU validation showed that all-32K VLM co-residency is not safe on two 24GB cards, so the runtime contract uses role-weighted KV budgets: Qwen3-VL 8B HQ/rescue at 32K plus Qwen3-VL 2B semantic at 16K on GPU0, Granite 4.0 3B Vision at 16K plus Qwen3-VL-Embedding 2B at 2K on GPU1, with Qwen3-Embedding-4B text embeddings treated as RTX 3090/offload/on-demand until cross-node serving is wired.

**Tech Stack:** Docker Compose GPU reservations, NVIDIA Container Toolkit, voipmonitor/vLLM cu130, vLLM OpenAI-compatible server, Qwen3-VL, Granite 4.0 Vision, Hugging Face TEI, pytest.

---

### Task 1: Encode Source-Backed GPU Placement In Tests

**Files:**
- Modify: `tests/unit/test_compose_model_profiles.py`

- [x] **Step 1: Update tests to reject `gpus: all` for live model services**

Expected assertions:
- Each live model service has `deploy.resources.reservations.devices[0].driver == "nvidia"`.
- Each live model service has `device_ids` pointing at the correct host GPU variable.
- Each live model service has `capabilities == ["gpu"]`.
- Each live model service sets `STRUCTURA_CUDA_VISIBLE_DEVICES == "0"` and `CUDA_DEVICE_ORDER == "PCI_BUS_ID"`.
- Each live model service has `ipc: host`, `shm_size`, and `ulimits`.

- [x] **Step 2: Run the targeted test and verify RED**

Run: `python3 -m pytest -q tests/unit/test_compose_model_profiles.py`

Expected before implementation: failure because services still use `gpus: all` and do not have explicit device reservations.

### Task 2: Implement Deterministic Compose GPU Binding

**Files:**
- Modify: `compose.yaml`

- [x] **Step 1: Add a reusable live-model runtime anchor**

Add a top-level YAML extension with `ipc: host`, shared memory, and GPU-friendly ulimits.

- [x] **Step 2: Replace live model `gpus: all` with explicit device reservations**

For each live model service, add:
- `device_ids: ["${STRUCTURA_MODEL_<NAME>_GPU:-N}"]`
- `capabilities: [gpu]`
- `STRUCTURA_CUDA_VISIBLE_DEVICES: "0"`
- `CUDA_DEVICE_ORDER: PCI_BUS_ID`

- [x] **Step 3: Keep live services bound to loopback ports**

Do not expose model ports publicly; retain `127.0.0.1` default binding.

- [x] **Step 4: Run Compose config checks**

Run:
- `docker compose --profile models-live config -q`
- `docker compose --profile visual-embed-live config -q`

Expected: both commands pass.

### Task 3: Expose Model Memory/Context Knobs

**Files:**
- Modify: `compose.yaml`
- Modify: `workers/model_services/start_granite_vllm.sh`
- Modify: `workers/model_services/start_qwen_vllm.sh`
- Modify: `workers/model_services/start_visual_embed_vllm.sh`

- [x] **Step 1: Add Granite vLLM flags**

Expose `STRUCTURA_GRANITE_MAX_MODEL_LEN`, `STRUCTURA_GRANITE_GPU_MEMORY_UTILIZATION`, `STRUCTURA_GRANITE_MAX_NUM_SEQS`, and `STRUCTURA_GRANITE_LIMIT_MM_PER_PROMPT`; forward them to the Granite vLLM wrapper.

- [x] **Step 2: Disable video and right-size context/concurrency**

Default all VLM services to image-only prompts. Use reduced `max_num_seqs` and explicit `max_model_len` to leave enough KV cache without trying to reserve full upstream defaults.

- [x] **Step 3: Run targeted unit tests**

Run: `python3 -m pytest -q tests/unit/test_compose_model_profiles.py`

Expected: pass.

### Task 4: Make GPU Smoke First-Load Aware

**Files:**
- Modify: `scripts/gpu/phase8_5_model_smoke.sh`

- [x] **Step 1: Replace immediate health failure with bounded readiness wait**

Poll `/healthz` then `/health` for each service until success or timeout. Default timeout should handle first model load/download; make it configurable with `STRUCTURA_MODEL_SMOKE_HEALTH_TIMEOUT_SECONDS`.

- [x] **Step 2: Keep inference probes required**

Do not accept container health alone. The script must still run `scripts/gpu/probe_phase8_5_live_models.py`.

- [x] **Step 3: Keep model-backed corpus evidence explicit**

- [x] **Step 4: Add managed smoke mode**

The smoke script now supports `STRUCTURA_MODEL_SMOKE_MANAGE_COMPOSE=1` to validate
co-resident Blackwell VLM services first, temporarily offload GPU1 VLM services
for Qwen3-Embedding-4B text embedding validation, and then restore the VLM services.
This preserves truthful validation without pretending all five model surfaces fit
with identical 32K KV budgets on two 24GB Blackwell cards.

Service transitions use forced container removal rather than plain stop so a
failed or interrupted offload step cannot leave a GPU-resident model blocking
the next restore.

Do not fabricate a corpus manifest. Keep `scripts/run_model_corpus.py --require-model-backed`; if the private manifest is absent, the smoke gate must report that as a real remaining blocker.

### Task 5: Verify Locally And On GPU

**Files:**
- No source edits unless verification exposes a defect.

- [x] **Step 1: Local deterministic checks**

Run:
- `python3 -m ruff check .`
- `python3 -m ruff format --check .`
- `python3 scripts/validate_contracts.py`
- `python3 -m pytest -q tests/unit/test_compose_model_profiles.py`
- `docker compose --profile models-live config -q`
- `docker compose --profile visual-embed-live config -q`

- [x] **Step 2: Commit and push**

Commit only relevant files; do not stage `.DS_Store`.

- [x] **Step 3: GPU deterministic checks**

Pull to `/tank/repos/structura` and run the same deterministic checks with `/tank/venvs/structura/bin/python`.

- [ ] **Step 4: GPU live model validation**

Recreate the live model services, confirm correct GPU placement, and run:

`STRUCTURA_MODEL_MODE=live PYTHON=/tank/venvs/structura/bin/python bash scripts/gpu/phase8_5_model_smoke.sh`

Expected: live inference probes must pass. If the private model-backed corpus manifest is absent, report that as an explicit blocked release gate rather than signing off.
