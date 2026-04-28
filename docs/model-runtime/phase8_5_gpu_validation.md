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
STRUCTURA_MODEL_MODE=live bash scripts/gpu/phase8_5_model_smoke.sh
```

The smoke gate checks service health and performs one minimal live inference request
against Qwen HQ/rescue, Qwen semantic, Granite, text embeddings, and visual
embeddings before evaluating the private corpus manifest.

The committed example model-corpus manifest is deterministic documentation only.
Release validation must use a private `phase8_5_model_manifest.json` with
`fixtureType = "model_backed"`.
