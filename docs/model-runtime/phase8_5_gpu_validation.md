# Phase 8.5 GPU Model Validation

Phase 8.5 is not complete with fixture-only behavior. The canonical GPU node must
prove live model services are reachable and that private model-backed corpus evidence
passes thresholds.

```bash
ssh -i /Users/brennanconley/vibecode/infx/ubuntu24_ed25519 bgconley@10.25.0.50
cd /tank/repos/structura
git pull --ff-only
docker compose --profile models-live up -d \
  model-qwen-semantic model-qwen model-granite model-vl-embed
docker compose --profile text-embed-live up -d model-embed
STRUCTURA_MODEL_MODE=live PYTHON=/tank/venvs/structura/bin/python bash scripts/gpu/phase8_5_model_smoke.sh
```

On the current 2x 24GB Blackwell node, `models-live` is the co-resident VLM
profile: Qwen3-VL 2B semantic and Qwen3-VL 8B HQ/rescue on GPU0, plus Granite
4.0 3B Vision and Qwen3-VL-Embedding 2B visual embeddings on GPU1. These
services use reduced vLLM `gpu_memory_utilization` settings so the KV cache is
large enough for the configured context without each process attempting to
reserve most of a 24GB card.

Qwen3-Embedding-4B text embeddings remain an offload/on-demand profile on the
two-Blackwell node. Validation showed the TEI process uses roughly 8GB of GPU
memory; running it beside both Granite and visual embeddings on the second
Blackwell leaves no hardened safety margin. The preferred always-available text
embedding placement is the RTX 3090 node once cross-node serving is wired.

Use managed smoke mode to validate co-resident Blackwell VLM services first,
then temporarily offload GPU1 VLM services to validate text embeddings, and
finally restore the VLM services:

```bash
STRUCTURA_MODEL_MODE=live \
STRUCTURA_MODEL_SMOKE_MANAGE_COMPOSE=1 \
PYTHON=/tank/venvs/structura/bin/python \
bash scripts/gpu/phase8_5_model_smoke.sh
```

The smoke gate waits for first-load health and performs minimal live inference
requests against Qwen HQ/rescue, Qwen semantic, Granite, visual embeddings, and
text embeddings before evaluating the private corpus manifest.

The Blackwell runtime uses explicit Docker Compose GPU reservations rather than
only `gpus: all`. Each live model container is assigned a host GPU with
`deploy.resources.reservations.devices[*].device_ids`, then sees that device as
inside-container `CUDA_VISIBLE_DEVICES=0` with `CUDA_DEVICE_ORDER=PCI_BUS_ID`.
This avoids vLLM using the wrong card or inheriting NVIDIA runtime sentinel
values before model inspection.

The default memory/context settings are intentionally conservative:

- Qwen3-VL 2B semantic: always-on, image-only, 32K context, low concurrency.
- Qwen3-VL 8B HQ/rescue: always-on in `models-live`; it shares the first
  Blackwell card with the 2B semantic service and uses reduced KV over-reservation
  rather than on-demand unload/reload.
- Granite 4.0 3B Vision: high-priority structured extraction, image-only, 32K
  context rather than the much larger upstream default.
- Visual embeddings: always-on in `models-live` on GPU1 with native
  2048-dimensional Qwen3-VL-Embedding output. It rejects the OpenAI `dimensions`
  override, so do not configure Structura visual embeddings as 1024-dimensional
  unless a different backend is explicitly selected.
- Text embeddings: offload/on-demand on the two-Blackwell node; prefer the RTX
  3090 node for always-available text embeddings.

If smoke output shows KV-cache preemption, increase that service's
`STRUCTURA_*_GPU_MEMORY_UTILIZATION` or reduce `STRUCTURA_*_MAX_NUM_SEQS`.
If startup OOMs, reduce `max_model_len`, `max_num_seqs`, or avoid co-residency
for that profile.

The committed example model-corpus manifest is deterministic documentation only.
Release validation must use a private `phase8_5_model_manifest.json` with
`fixtureType = "model_backed"`.
