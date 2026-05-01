# Structura Model Runtime Profiles

Phase 8.5 separates deterministic fixture behavior from live local model services.
The API and workers stay lightweight; Qwen, Granite, and embedding backends run as
separate internal services behind Compose profiles.

## Profiles

```text
models-placeholder
  Health-only placeholders. Useful for compose shape checks. Not inference.

models-live
  Always-on live model services: model-qwen-semantic, model-granite, model-embed.

visual-embed-live
  Scheduled/offline visual embedding service: model-vl-embed.
```

## GPU Placement

```text
model-qwen-semantic -> Blackwell GPU 0, Qwen3-VL-8B-Instruct-FP8 Smart Parse semantic annotation
model-granite       -> Blackwell GPU 1, Granite 4.0 3B Vision
model-embed         -> GPU 1 by default for single-node validation; RTX 3090 node preferred for production, Qwen3-Embedding-4B at 1536 dimensions
model-vl-embed      -> Blackwell scheduled/offline, Qwen3-VL-Embedding-2B at 2048 dimensions
```

Do not run Qwen semantic and Granite on the same 24 GB Blackwell card by default. Do not make
visual embedding always-on with Granite until a live concurrency benchmark proves it.

## Image Policy

Release candidates must pin model images by tag and digest. Current Compose defaults
use the local SM120/cu130 vLLM image (`voipmonitor/vllm:cu130`) for Qwen, Granite,
and visual embeddings, plus Hugging Face TEI CUDA for text embeddings. Treat these
as operational defaults for GPU smoke, not final release pinning: release evidence
still requires digest-pinned images and private model-backed corpus results.
