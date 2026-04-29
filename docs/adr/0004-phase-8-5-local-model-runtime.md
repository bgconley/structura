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
- Qwen3-VL-4B semantic planning and Granite 4.0 3B Vision extraction are the default
  Phase 8.5 live-model priorities. Qwen3-VL-8B remains an explicit high-quality/rescue
  contract for future evaluation, not an automatically invoked runtime dependency.
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
- `model-qwen-semantic` runs the Qwen3-VL-4B semantic profile as the always-on Smart
  Parse annotator. It preserves the four-page semantic fan-in shape used by the historical
  2B path, but its page images are planner-resolution only through Qwen's 32x visual-token
  guidance: 256 minimum and 2560 maximum visual tokens per image.
- `model-qwen` / Qwen3-VL-8B is disabled/deferred in the active runtime. The HQ/rescue
  contracts remain visible, but default application logic must not silently remap them or
  invoke Qwen3-VL-8B without explicit user intent.
- `model-granite` owns structured bills, invoices, receipts, EOBs, tables, charts, forms, and
  semantic KVP extraction. It is the highest-priority GPU1 VLM at 16K because it receives targeted
  Docling-grounded crops/regions, not whole-document prompts.
- `model-embed` serves Qwen3-Embedding-4B at 1536 dimensions as an on-demand service on the current
  single-node Blackwell Compose deployment. GPU validation showed it consumes roughly 8GB; co-running
  it with both Granite and visual embeddings on one 24GB Blackwell card leaves no hardened safety
  margin, so the RTX 3090 path remains the preferred always-available text embedding placement once
  cross-node serving is wired.
- `model-vl-embed` serves Qwen3-VL-Embedding at its native 2048 dimensions with a short 2K context
  budget co-resident with Granite on GPU1.
- The Phase 8.5 GPU smoke script supports staged validation: bring up Qwen3-VL-4B Smart
  Parse, Granite, visual embeddings, and text embeddings as separate gates, preserving the
  measured Granite/visual-embed co-residency profile and avoiding hidden Qwen3-VL-8B calls.
- Fixture mode is explicitly named and test-only. Live/required mode must call configured model
  services and must fail safely when unavailable.
- `source_engine = qwen3_vl_4b`, `source_engine = qwen3_vl_8b`, or
  `source_engine = granite_vision_3b` may be persisted only after the corresponding live adapter
  returns a successful model response.
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
- Cross-node text embedding serving on the RTX 3090 node should be wired and benchmarked before
  treating text embeddings as an always-on local cluster surface.
