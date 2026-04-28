# Phase 8.5 GPU Model Validation

Phase 8.5 is not complete with fixture-only behavior. The canonical GPU node must
prove live model services are reachable and that private model-backed corpus evidence
passes thresholds.

```bash
ssh -i /Users/brennanconley/vibecode/infx/ubuntu24_ed25519 bgconley@10.25.0.50
cd /tank/repos/structura
git pull --ff-only
docker compose --profile models-live up -d model-qwen-semantic model-qwen model-granite model-embed
docker compose --profile visual-embed-live up -d model-vl-embed
STRUCTURA_MODEL_MODE=live PYTHON=/tank/venvs/structura/bin/python bash scripts/gpu/phase8_5_model_smoke.sh
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
- Qwen3-VL 8B HQ/rescue: live-capable but should be treated as on-demand until
  co-residency benchmarks prove stable margins.
- Granite 4.0 3B Vision: high-priority structured extraction, image-only, 32K
  context rather than the much larger upstream default.
- Text embeddings and visual embeddings: model-backed surfaces, but visual
  embedding remains a batch/offline candidate if it competes with Granite.

If smoke output shows KV-cache preemption, increase that service's
`STRUCTURA_*_GPU_MEMORY_UTILIZATION` or reduce `STRUCTURA_*_MAX_NUM_SEQS`.
If startup OOMs, reduce `max_model_len`, `max_num_seqs`, or avoid co-residency
for that profile.

The committed example model-corpus manifest is deterministic documentation only.
Release validation must use a private `phase8_5_model_manifest.json` with
`fixtureType = "model_backed"`.
