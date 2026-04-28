# Phase 8.5 GPU Model Validation

Phase 8.5 is not complete with fixture-only behavior. The canonical GPU node must
prove live model services are reachable and that private model-backed corpus evidence
passes thresholds.

```bash
ssh -i /Users/brennanconley/vibecode/infx/ubuntu24_ed25519 bgconley@10.25.0.50
cd /tank/repos/structura
git pull --ff-only
docker compose --profile models-live up -d model-qwen-semantic model-granite
docker compose --profile qwen-hq-live up -d model-qwen
docker compose --profile text-embed-live up -d model-embed
docker compose --profile visual-embed-live up -d model-vl-embed
STRUCTURA_MODEL_MODE=live PYTHON=/tank/venvs/structura/bin/python bash scripts/gpu/phase8_5_model_smoke.sh
```

On the current 2x 24GB Blackwell node, do not start every live model at once.
`models-live` is the always-on core profile: Qwen3-VL 2B semantic on GPU0 and
Granite 4.0 3B Vision on GPU1. Qwen3-VL 8B HQ/rescue, Qwen3-Embedding-4B text
embeddings, and visual embeddings are explicit on-demand/offload profiles
because co-residency can leave vLLM with no available KV-cache blocks. Use the
managed smoke mode to validate the full model set sequentially and restore the
always-on core services afterward:

```bash
STRUCTURA_MODEL_MODE=live \
STRUCTURA_MODEL_SMOKE_MANAGE_COMPOSE=1 \
PYTHON=/tank/venvs/structura/bin/python \
bash scripts/gpu/phase8_5_model_smoke.sh
```

The smoke gate waits for first-load health and performs one minimal live inference
request against Qwen HQ/rescue, Qwen semantic, Granite, text embeddings, and
visual embeddings before evaluating the private corpus manifest.

The Blackwell runtime uses explicit Docker Compose GPU reservations rather than
only `gpus: all`. Each live model container is assigned a host GPU with
`deploy.resources.reservations.devices[*].device_ids`, then sees that device as
inside-container `CUDA_VISIBLE_DEVICES=0` with `CUDA_DEVICE_ORDER=PCI_BUS_ID`.
This avoids vLLM using the wrong card or inheriting NVIDIA runtime sentinel
values before model inspection.

The default memory/context settings are intentionally conservative:

- Qwen3-VL 2B semantic: always-on, image-only, 32K context, low concurrency.
- Qwen3-VL 8B HQ/rescue: on-demand by default; it shares the first Blackwell
  card with the 2B semantic service and should not be co-resident unless a
  benchmark proves stable KV-cache margins.
- Granite 4.0 3B Vision: high-priority structured extraction, image-only, 32K
  context rather than the much larger upstream default.
- Text embeddings and visual embeddings: model-backed surfaces, but both remain
  batch/offline or RTX 3090 offload candidates on this hardware. Qwen3-Embedding
  4B consumed enough memory to conflict with Granite on a 24GB Blackwell card.

If smoke output shows KV-cache preemption, increase that service's
`STRUCTURA_*_GPU_MEMORY_UTILIZATION` or reduce `STRUCTURA_*_MAX_NUM_SEQS`.
If startup OOMs, reduce `max_model_len`, `max_num_seqs`, or avoid co-residency
for that profile.

The committed example model-corpus manifest is deterministic documentation only.
Release validation must use a private `phase8_5_model_manifest.json` with
`fixtureType = "model_backed"`.
