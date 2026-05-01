# Phase 8.5 GPU Model Validation

Phase 8.5 is not complete with fixture-only behavior. The canonical GPU node must
prove live model services are reachable and that private model-backed corpus evidence
passes thresholds.

```bash
ssh -i /Users/brennanconley/vibecode/infx/ubuntu24_ed25519 bgconley@10.25.0.50
cd /tank/repos/structura
git pull --ff-only
STRUCTURA_MODEL_MODE=live PYTHON=/tank/venvs/structura/bin/python bash scripts/gpu/phase8_5_model_smoke.sh
```

On the current 2x 24GB Blackwell node, `models-live` is the co-resident VLM
profile with role-weighted context budgets:

- GPU0: Qwen3-VL-8B-Instruct-FP8 Smart Parse semantic service at 32K context.
- GPU1: Granite 4.0 3B Vision at 16K context, then Qwen3-VL-Embedding 2B at 2K.
- Qwen3-Embedding-4B text embeddings remain offload/on-demand on the two-Blackwell
  node; prefer the RTX 3090 node for always-available text embeddings once
  cross-node serving is wired.

Use managed smoke mode to start the highest-context VLM on each card first, then
the lower-context companion services, then temporarily offload GPU1 VLM services
to validate text embeddings, and finally restore the co-resident VLM services:

```bash
STRUCTURA_MODEL_MODE=live \
STRUCTURA_MODEL_SMOKE_MANAGE_COMPOSE=1 \
PYTHON=/tank/venvs/structura/bin/python \
bash scripts/gpu/phase8_5_model_smoke.sh
```

The smoke gate waits for first-load health and performs minimal live inference
requests against Qwen Smart Parse, Granite, visual embeddings, and text
embeddings before evaluating the private corpus manifest.

The Blackwell runtime uses explicit Docker Compose GPU reservations rather than
only `gpus: all`. Each live model container is assigned a host GPU with
`deploy.resources.reservations.devices[*].device_ids`, then sees that device as
inside-container `CUDA_VISIBLE_DEVICES=0` with `CUDA_DEVICE_ORDER=PCI_BUS_ID`.
This avoids vLLM using the wrong card or inheriting NVIDIA runtime sentinel
values before model inspection.

The default memory/context settings are intentionally conservative:

- Qwen3-VL-8B-Instruct-FP8 Smart Parse: 32K context, image-only, low concurrency;
  highest allocation because it owns semantic inventory and routing.
- Granite 4.0 3B Vision: 16K context, image-only, low concurrency; targeted
  crops/regions should keep extraction prompts narrower than full-document Qwen.
- Visual embeddings: 2K context with native 2048-dimensional Qwen3-VL-Embedding
  output. It rejects the OpenAI `dimensions` override, so do not configure
  Structura visual embeddings as 1024-dimensional unless a different backend is
  explicitly selected.
- Text embeddings: offload/on-demand on the two-Blackwell node; prefer the RTX
  3090 node for always-available text embeddings.

If smoke output shows KV-cache preemption, increase that service's
`STRUCTURA_*_GPU_MEMORY_UTILIZATION` or reduce `STRUCTURA_*_MAX_NUM_SEQS`.
If startup OOMs, reduce `max_model_len`, `max_num_seqs`, or avoid co-residency
for that profile.

The committed example model-corpus manifest is deterministic documentation only.
Release validation must use a private `phase8_5_model_manifest.json` with
`fixtureType = "model_backed"`.
