# Structura Model Runtime Profiles

Phase 8.5 separates deterministic fixture behavior from live local model services.
The API and workers stay lightweight; Qwen, Granite, and embedding backends run as
separate internal services behind Compose profiles.

## Profiles

```text
models-placeholder
  Health-only placeholders. Useful for compose shape checks. Not inference.

models-live
  Always-on live model services: model-qwen, model-granite, model-embed.

visual-embed-live
  Scheduled/offline visual embedding service: model-vl-embed.
```

## GPU Placement

```text
model-qwen      -> Blackwell GPU 0, Qwen3-VL-8B
model-granite   -> Blackwell GPU 1, Granite 4.0 3B Vision
model-embed     -> RTX 3090 node, Qwen3-Embedding-4B at 1536 dimensions
model-vl-embed  -> Blackwell scheduled/offline, Qwen3-VL-Embedding-2B at 1024 dimensions
```

Do not run Qwen and Granite on the same 24 GB Blackwell card by default. Do not make
visual embedding always-on with Granite until a live concurrency benchmark proves it.

## Image Policy

Release candidates must pin model images by tag and digest. Experimental SM120/cu130
images are allowed only behind explicit environment variables and must not be treated
as release evidence until GPU smoke and corpus gates pass.

The current Compose defaults are placeholders for image selection. Operators should
set `STRUCTURA_MODEL_*_IMAGE` to approved image references before enabling
`STRUCTURA_MODEL_MODE=live`.
