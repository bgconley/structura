# ADR 0004: Phase 8.5 Local Model Runtime

Date: 2026-04-28

## Status

Accepted

## Context

Phase 8 introduced difficult-document seams, but release review found that visual retrieval and
handwriting routes were still fixture-backed. Phase 9 analysis must not be built on fake model
outputs, fake provenance, or unverified structure extraction.

## Decisions

- Phase 8.5 is mandatory before Phase 9 analysis.
- Qwen3-VL-8B and Granite 4.0 3B Vision are equal priorities.
- Live Qwen/Granite/visual VLM services use the `voipmonitor/vllm:cu130` Blackwell-oriented vLLM
  image family unless benchmark evidence proves a better pinned image. Firecrawl-backed research
  found the voipmonitor RTX 6000 Pro docs describe that image as recommended for vLLM on SM120
  with Blackwell patches and FlashInfer.
- Docker Compose owns physical GPU placement through explicit GPU device reservations. Containers
  use `CUDA_DEVICE_ORDER=PCI_BUS_ID` and inside-container `CUDA_VISIBLE_DEVICES=0`; model scripts
  must not guess host GPU numbering after vLLM has started importing CUDA/PyTorch.
- `gpu_memory_utilization`, `max_model_len`, `max_num_seqs`, video disabling, and multimodal
  processor cache sizing are first-class runtime knobs. Lowering memory utilization can enable
  co-residency, but it reduces KV-cache capacity and must be checked with inference probes and
  preemption logs.
- `model-qwen-semantic` runs the Qwen3-VL-2B semantic profile as the always-on semantic annotator.
- `model-qwen` runs the Qwen3-VL-8B HQ/rescue profile and owns handwriting, degraded OCR rescue,
  visual fallback, and later cited analysis support; it may be on-demand if co-residency does not
  pass GPU validation.
- `model-granite` owns structured bills, invoices, receipts, EOBs, tables, charts, forms, and
  semantic KVP extraction.
- `model-embed` runs on the RTX 3090 path and serves Qwen3-Embedding-4B at 1536 dimensions.
- `model-vl-embed` serves Qwen3-VL-Embedding at 1024 dimensions as scheduled/offline work until
  concurrency with Granite is benchmarked.
- Fixture mode is explicitly named and test-only. Live/required mode must call configured model
  services and must fail safely when unavailable.
- `source_engine = qwen3_vl_8b` or `source_engine = granite_vision_3b` may be persisted only after
  the corresponding live adapter returns a successful model response.
- Model clients use fixed configured base URLs, no user-provided target URLs, bounded response
  sizes, timeouts, vector-shape validation, and redacted health/error metadata.

## Consequences

- API and web images stay lightweight; Qwen, Granite, and embedding serving remain separate
  runtime concerns.
- Phase 9 must consume accepted canonical facts, review-required uncertainty, ACL-safe evidence,
  and model provenance rather than raw model outputs.
- Release readiness requires model-backed corpus evidence in addition to deterministic CI.

## Deferred Work

- Final image references must be pinned by digest after the selected vLLM/TEI/Granite serving
  images are built and benchmarked on the GPU node.
- `model-vl-embed` should not become always-on with Granite until a Blackwell concurrency benchmark
  proves memory and latency margins.
