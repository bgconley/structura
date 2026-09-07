# Structura Phase 8.5 Model And Embedding Services Implementation Plan

Current completion tracking: [STRUCTURA_PRODUCTION_COMPLETION_PLAN.md](STRUCTURA_PRODUCTION_COMPLETION_PLAN.md), its [extraction/retrieval packages](docs/plans/production-completion/extraction-retrieval.md), and accepted [ADR 0008](docs/adr/0008-qwen38-27b-ingestion.md)/[ADR 0009](docs/adr/0009-qwen-native-document-parsing.md). The user selected the existing Oxcart **Qwen3.8-27B BF16** service and Qwen-native parsing. Model/parser direction is complete; implementation, migration, source fidelity and release gates remain open. These documents preserve the Phase 8.5 stop point. Historical Docling/8B/Granite task instructions and launch commands below are migration context, not the current execution checklist or proof of 27B readiness.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Qwen-native full-document parsing and extraction on the existing Oxcart Qwen3.8-27B BF16 service under [ADR 0009](docs/adr/0009-qwen-native-document-parsing.md). Preserve original evidence, complete searchable structure, truthful provenance, validation and review. Docling is temporary migration/comparison support. Complete real text/visual embeddings on the proposed Blackbird PRO 4000 for both ingestion/reindexing and search queries before Phase 9.

**Architecture:** Phase 8.5 inserts a model-runtime foundation between Phase 8 and Phase 9. API, workers, and services keep deterministic fixture adapters for tests, but production/live GPU mode must use explicit HTTP model adapters with truthful provenance, bounded inputs, dimension validation, and model-backed golden evidence.

**Tech Stack:** FastAPI/Python workers, PostgreSQL/pgvector, Docker Compose profiles, authenticated existing Oxcart Qwen3.8-27B BF16 serving, explicit task/schema adapters, Qwen3-Embedding and Qwen3-VL-Embedding on a measured retrieval profile. Blackbird's 24 GB PRO 4000 is proposed for embeddings; its Gemma service is excluded.

## Phase 8.5 Realignment

Selected target pipeline, pending implementation and migration:

```text
Immutable original + lightweight page inventory/rendering/native-text layer
-> Qwen3.8-27B BF16 full structural parse and bounded extraction on Oxcart
-> versioned searchable text, pages/elements/tables/chunks and typed candidates
-> validators / provenance / review policy
-> canonical facts + evidence/search layer
```

27B also owns classification and semantic planning through distinct task contracts. ADR 0009 replaces mandatory Docling and selection-only extraction; native parsing is the implementation target. The original remains the source, while Qwen's parse is the current derived structural representation. Preserve native/model origins through all consumers: copying Qwen transcription does not make it independently verified. Docling, Granite and 8B retain historical/comparison lineage without a release veto. No model output bypasses validation or review.

Active operator-visible modes:

- `smart`: planned 27B semantic task with explicit current model/prompt/schema lineage; migrate the existing manifest harness without relabeling historical records.
- `review_only`: uncertain output routes to review without hidden automatic
  escalation.

Persist these intent fields in semantic job payloads and audit-visible job data:

- `semantic_quality_mode`: `smart`
- `requested_by_user_id`
- `user_intent_reason`

Valid document-quality outcomes are `extracted_cleanly`, `needs_human_review`,
`insufficient_signal`, and `no_extraction_target`. Reserve `pipeline_failed` for
runtime/system defects only: model timeout/unavailable, invalid model response
after retry, worker crash, storage or DB error, contract violation, and related
operational failures.

Document-quality ambiguity must never dead-letter jobs. Runtime failures should
retry and then dead-letter/admin-health as appropriate.

---

## Why Phase 8.5 Exists

Phase 8 shipped the product seams for difficult-document detection, visual retrieval, review-required handwriting, and model placeholders. The release-readiness audit found that those seams are not enough for Phase 9 analysis:

- Visual embeddings are not allowed to be descriptor-text or byte-hash fixtures in live mode. They must be generated from image content by a real visual embedding model.
- Qwen provenance is not allowed unless Qwen was actually invoked.
- Layout-preserving searchable parsing and extraction are required for ordinary prose, bills, invoices, EOBs, statements, forms, tables and charts. ADR 0009 supersedes the previous mandatory Docling/selection-only pipeline. Historical converter output remains readable; the new pipeline must work with Docling disabled.
- Phase 9 analysis must not be built on fake model outputs, unverified structure extraction, or undocumented model service assumptions.

Phase 8.5 is therefore a mandatory stop point before Phase 9.

## Final Model Priority Decision

Use the existing Qwen3.8-27B BF16 Oxcart service for all generative ingestion roles. Prioritize truthful profile/adapter/schema migration and bounded same-27B simplification before further work specific to the older model arrangement. There is no separate automatic High Quality/rescue service. Granite is an optional historical/comparison path. A new 8B-versus-27B benchmark is not a model-selection prerequisite.

Qwen3.8-27B BF16 owns:

- full searchable transcription, structure, reading order and tables grounded to original pages;
- semantic annotation and bounded routing metadata over versioned source/parse IDs;
- ambiguity flags and review hints that do not become canonical facts;
- classification, table/KVP selection and bounded extraction candidates under explicit task contracts and source verification.

Uncertainty stays on review/skip/abstention paths until a future explicit plan
re-evaluates a separate escalation runtime.

Bounded Qwen visual tasks cover:

- ordinary and difficult-page structural parsing from original page images;
- extraction with original-coordinate evidence and explicit missing/ambiguous content;
- review-required model values; matching a model's own transcript is not independent verification.

Text embeddings own:

- document/chunk encoding during ingestion and reindexing, plus compatible query encoding at search time;
- default text-heavy retrieval;
- chunk and document retrieval;
- filter-aware semantic search from Phase 5.

Visual embeddings own:

- selected original-page encoding during ingestion/reindexing, plus compatible visual-search query encoding;
- selective image/page retrieval for low-text, handwriting, degraded, image-heavy, or layout-distinctive pages;
- visual search candidate recall, not canonical fact authority.

## Historical research evidence summary

The following research informed the former topology. It does not override ADR 0008 or require a new 27B fit/quantization experiment on Blackbird. Keep actual embedding model/dimension compatibility; remeasure their proposed Blackbird deployment.

Research was collected under `.firecrawl/model-serving-research/`. Important source conclusions:

- NVIDIA RTX PRO 4000 Blackwell has 24 GB GDDR7 and fifth-generation Tensor Cores with FP4 support, so Blackwell-specific FP4/NVFP4 paths can materially change what fits on one card.
- Qwen3-VL public materials emphasize OCR, blur/tilt robustness, long-document structure parsing, long context, and multimodal reasoning. vLLM has explicit Qwen3-VL recipes and recommends image-only settings such as disabling video inputs to preserve memory.
- Granite 4.0 3B Vision public materials emphasize enterprise document understanding, table extraction, chart understanding, semantic KVP extraction, full-page table benchmarks, and Docling integration.
- IBM Granite-Docling materials reinforce that structure preservation matters for downstream RAG and analysis, especially tables, forms, charts, captions, equations, and layout relations.
- Qwen3-Embedding supports 0.6B, 4B, and 8B sizes, custom output dimensions, and TEI deployment. Qwen3-Embedding-4B is the default accuracy/fit target for the RTX 3090.
- Qwen3-VL-Embedding supports 2B and 8B variants, text/image/video retrieval, and vLLM examples. Live validation showed the selected vLLM endpoint returns native 2048-dimensional vectors and rejects the `dimensions` override, so Structura uses the 2048-dimensional visual index unless a different backend proves safe down-projection support.
- The voipmonitor/cu130 work is useful evidence for SM120/cu130 experimentation, but it is not a project source of truth. Use it only through pinned images/digests and live benchmark gates.

Primary source URLs:

- `https://www.nvidia.com/content/dam/en-zz/Solutions/design-visualization/quadro-product-literature/workstation-datasheet-blackwell-rtx-pro-4000-nvidia-3662515.pdf`
- `https://github.com/QwenLM/Qwen3-VL`
- `https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3-VL.html`
- `https://docs.vllm.ai/en/stable/features/multimodal_inputs/`
- `https://huggingface.co/blog/ibm-granite/granite-4-vision`
- `https://huggingface.co/ibm-granite/granite-4.0-3b-vision`
- `https://www.ibm.com/granite/docs/use-cases/multimodal-rag`
- `https://www.ibm.com/new/announcements/granite-docling-end-to-end-document-conversion`
- `https://arxiv.org/abs/2408.09869`
- `https://huggingface.co/Qwen/Qwen3-Embedding-4B`
- `https://github.com/QwenLM/Qwen3-VL-Embedding`
- `https://github.com/voipmonitor/rtx6kpro/blob/master/inference-engines/vllm.md`

## Operating Rules

- Do not start Phase 9 until Phase 8.5 gates pass or the user explicitly accepts documented release blockers.
- Do not inspect or rely on anything under `archive/`.
- Before coding a task, re-read that task's **Fresh Context** files with bounded reads for large files.
- Keep API routes thin. Model behavior belongs in adapters, services, workers, or model-service containers.
- Keep model services isolated from API/web images. Do not add Qwen, Granite, Torch CUDA, vLLM, TEI, or NVIDIA stack dependencies to the API image unless an explicit ADR approves it.
- Deterministic gateways are test fixtures only. In live GPU validation, they must be disabled or clearly reported as fixture mode.
- A model output may claim `source_engine = qwen` or `source_engine = granite` only when the corresponding live model adapter successfully invoked that service.
- Default ingestion uses the selected 27B profile. Do not auto-run a second semantic pass or silently fall back to 8B/Granite on ordinary `needs_review`.
- Do not treat low confidence, high-risk document family, or human-review policy as `pipeline_failed`.
- Do not conflate human review required with extraction failure.
- Do not let Qwen annotations become canonical facts or Granite candidates bypass validators/review policy.
- Do not create repeated rescue loops or unbounded semantic/Granite fanout.
- Do not log raw document text, image bytes, prompts, responses, object paths, presigned URLs, or model input file paths.
- Model services must not fetch arbitrary external URLs. Pass sanitized local files mounted under a narrow allowed directory or base64 payloads through internal-only APIs.
- Use the existing authenticated Oxcart endpoint and restricted cross-host retrieval endpoints under ADRs 0007/0008; no public model exposure or broad raw-storage mount is implied.
- Every model call must have timeout, max input size, retry/dead-letter semantics, model profile metadata, and redacted error behavior.

## Tightened Execution Order

1. Register the new 27B engine/task profiles, endpoint authentication, schemas, bounded final-answer parsing and truthful lineage under X-01/ADR 0008.
2. Remove 8B-specific identity assumptions from adapter/schema/budget selection and align runtime config, provenance, UI and reports without rewriting historical identities.
3. Integrate shared job/run ownership before domain publication; preserve uncertainty as review/partial/abstention rather than automatic escalation.
4. Prove authenticated 27B semantic, classification, selection and image extraction calls, adapting the existing semantic canary to the selected profile before full-corpus work.
5. Implement thin source handling and the provider-neutral full parse contract under ADR 0009/X-01/X-03. Migrate `docling_json` and hardcoded Docling origins before new output reaches claims, review or indexing. Preserve ordinary full text, all pages, tables, continuation, exact native source when useful and honest model transcription.
6. Complete authoritative claims, per-document orchestration and atomic current-parse/projection activation. Preserve historical evidence and later human corrections across rerun/reindex/rollback. Retire legacy converter dependencies only after Docling-free functionality and parser recovery gates.
7. Adapt provider-neutral scoring and private/resident corpus runners for actual 27B outputs. Old-model comparisons are optional; annotated source truth and release gates remain required.
8. Validate real text/visual embeddings on the measured Blackbird profile alongside shared Oxcart ingestion/client load. Do not recreate the resident 27B model or borrow Blackbird's occupied PRO 6000.
9. Record current-model full-parse and extraction quality against annotated originals, UI/evidence, security/race/outage and concurrent-workload acceptance with Docling disabled before Phase 9. Docling agreement is not a gate.

## Required Artifact Set

Fresh context for the whole phase:

- `STRUCTURA_IMPLEMENTATION_PLAN.md`
- `STRUCTURA_PHASE_8_IMPLEMENTATION_PLAN.md`
- `STRUCTURA_PHASE_9_IMPLEMENTATION_PLAN.md`
- `AGENTS.md`
- `README.md`
- `compose.yaml`
- `.github/workflows/ci.yml`
- `.github/workflows/gpu-live-smoke.yml`
- `pro-merged-master-v1.2/docs/01_App_Specification.md`
- `pro-merged-master-v1.2/docs/05_Nonfunctional_Requirements_Security_Privacy_Observability.md`
- `pro-merged-master-v1.2/docs/06_Testing_QA_and_Release_Strategy.md`
- `pro-merged-master-v1.2/docs/09_Deployment_and_Runtime_Architecture.md`
- `pro-merged-master-v1.2/docs/11_Model_Routing_and_Output_Contracts.md`
- `pro-merged-master-v1.2/docs/12_Risk_Register_and_Open_Questions.md`
- `pro-merged-master-v1.2/docs/18_Filter_Aware_Vector_Search_Addendum.md`
- `pro-merged-master-v1.2/infrastructure/runtime_service_matrix.csv`
- `.firecrawl/model-serving-research/extracts/qwen3_vl_vllm_latest.md`
- `.firecrawl/model-serving-research/extracts/qwen_embedding.md`
- `.firecrawl/model-serving-research/extracts/qwen_vl_embedding.md`
- `.firecrawl/model-serving-research/extracts/granite_docling_rag.md`
- `.firecrawl/model-serving-research/extracts/docling_arxiv.md`
- `.firecrawl/model-serving-research/extracts/rtx4000.md`
- `.firecrawl/model-serving-research/extracts/rtx3090.md`
- `.firecrawl/model-serving-research/extracts/voipmonitor_rtx6kpro_vllm.md`
- `.firecrawl/model-serving-research/extracts/qwen3vl8b_nvfp4.md`

## Hardware And Runtime Topology

Accepted model direction and proposed retrieval placement:

```text
Oxcart, existing shared generation service:
  Qwen3.8-27B BF16
  served model qwen38-27b-bf16-oxcart, host port 18012
  full structural parsing / classification / semantic / extraction task contracts

Blackbird, PRO 4000 GPU 1 (proposed retrieval deployment):
  text embedding model, compatible 1536-dimensional vectors
  visual embedding model, compatible native 2048-dimensional vectors
  encode ingestion/reindex document chunks and pages plus search queries
  measure co-residency, query latency and indexing backlog

Blackbird, PRO 6000 GPU 0:
  existing unrelated Gemma service; excluded
```

Reuse the authenticated Oxcart endpoint without changing its resident service configuration. Measure Structura admission and impact on existing clients separately from Blackbird embedding capacity. See ADRs 0007/0008 and the completion execution strategy for ownership, NFS and rollback boundaries.

Pre-migration live settings retained as migration input (not the selected 27B configuration):

```text
STRUCTURA_MODEL_MODE=live
STRUCTURA_QWEN_SEMANTIC_PROFILE=qwen3-vl-8b-fp8-semantic:v1
STRUCTURA_QWEN_PROFILE=qwen3-vl-8b-instruct-nvfp4-local:v1
STRUCTURA_TEXT_EMBED_PROFILE=qwen3-embedding-4b-1536:v1
STRUCTURA_VISUAL_EMBED_PROFILE=qwen3-vl-embedding-2b-2048:v1
```

`STRUCTURA_GRANITE_PROFILE=granite-4.0-3b-vision-bf16:v1` is valid only when an
explicit Granite rollback/comparison profile is selected.

Test/CI fixture profile:

```text
STRUCTURA_MODEL_MODE=fixture
```

Fixture mode is allowed in unit tests, deterministic CI, and local no-GPU development. Fixture mode is not acceptable for Phase 8.5 live gate completion.

## Model Profile Registry

Migration note: the registry, runtime examples and Tasks 1–13 below retain original Docling/8B/Granite/3090 design detail. Their mandatory converter/provider choices, selection-only contract, provider-specific schema/origin fields and deployment commands are superseded by ADRs 0008/0009 and X-01–X-08. Preserve unchanged evidence/security semantics while implementing converter-neutral parse contracts, new 27B task profiles and truthful historical compatibility. Do not execute old bringup commands against the existing Oxcart service or treat an old profile constant as the 27B identity.

Create an explicit registry in code. The registry must make model identity, dimensions, modality, runtime backend, profile version, and expected service contract inspectable.

Initial profiles:

```text
qwen3-vl-8b-instruct-nvfp4-local:v1
  engine: qwen
  task: multimodal_generate
  model_family: Qwen3-VL
  base_model: Qwen/Qwen3-VL-8B-Instruct
  quantization: nvfp4
  backend: vllm-openai
  default_gpu: blackwell-0
  max_images_per_request: 4
  max_image_bytes: 10485760
  max_model_len: 32768
  source_engine: qwen3_vl_8b

qwen3-vl-8b-fp8-semantic:v1
  engine: qwen
  task: semantic_annotation
  model_family: Qwen3-VL
  base_model: Qwen/Qwen3-VL-8B-Instruct-FP8
  quantization: fp8
  kv_cache_dtype: fp8
  backend: vllm-openai
  default_gpu: blackwell-0
  max_images_per_request: 4
  max_image_bytes: 10485760
  max_model_len: 32768
  max_num_seqs: 1
  gpu_memory_utilization: 0.88
  prefix_caching: disabled
  visual_token_spatial_compression: 32
  visual_token_min_per_image: 256
  visual_token_max_per_image: 2560
  source_engine: qwen3_vl_8b

Qwen3-VL-8B FP8 Smart Parse uses the same four-page semantic image fan-in shape
used by the historical 2B/4B smart path. Exact Docling page coverage remains
mandatory; coverage, context-length, and truncation problems are contract/runtime
failures to fix, not triggers for hidden model escalation.
Smart Parse images are semantic-understanding resolution only: vLLM should receive

```json
{"size":{"shortest_edge":262144,"longest_edge":2621440}}
```

Qwen semantic-understanding prompts should carry Docling page/element/table IDs,
document outline, bounded text snippets, and table snippets. They should not
carry token-heavy element bbox arrays or page image hashes. Those remain in
Docling persistence and Granite extraction/evidence paths, but Qwen does not
need them to build semantic inventory and extraction intent.
`STRUCTURA_VLLM_MM_PROCESSOR_KWARGS={"size":{"shortest_edge":262144,"longest_edge":2621440}}`,
which corresponds to Qwen's 32x guidance at 256 to 2560 visual tokens per image.
Do not downscale Docling originals globally, and do not weaken Granite
page/crop/table inputs.

Semantic prompt version `phase8_5-semantic-smart-v3` is the active Smart Parse
contract. It changes the Qwen bias from sparse "highest-value only" routing to
bounded semantic inventory and extraction intent:

- emit all materially extractable grounded regions that could change factual
  coverage;
- classify every page by role/usefulness and preserve continuation groups across
  pages when the document structure supports them;
- flag weak Docling table signal and request full-page image context for Granite
  when visual tables are present;
- emit competing `document_type_candidates` with evidence terms when family fit is
  ambiguous;
- include semantic metadata (`importance`, `source_signal`, `coverage_role`,
  `extraction_scope`, `requires_full_page_image`, `must_extract_reason`,
  `negative_routing_reason`, `min_expected_items`, and advisory
  `visual_bbox_hint`) without promoting values to canonical facts.

The model-output schemas remain adapter contracts, not app persistence schemas.
Structura validates and structurally normalizes Qwen output, preserves
model-emitted semantic metadata in the semantic manifest, and keeps
validators/Granite/review policy as the promotion gate. Normalization must not
inject semantic intent such as family-specific continuation groups or full-page
image routing. Smart Granite fanout is capped at six region jobs per semantic
pass, with line-item/service/payment regions prioritized over repeated headers
and boilerplate.

Before rerunning the full private corpus after Qwen prompt or schema changes,
run the semantic-only canary with private expectations:

```bash
python scripts/gpu/run_phase8_5_semantic_canary.py \
  --mode qwen3-vl-8b-fp8-smart \
  --expectations-json /srv/structura/config/private-semantic-canary-expectations.json \
  --json-output /srv/structura/objects/exports/phase85-runs/semantic-canary.json \
  --pdf /path/to/document.pdf
```

The canary report must show Docling audit anchors/table signals, Qwen
document-family candidates, page role/usefulness coverage, source-signal and
extraction-scope coverage, page coverage, fan-in/fallback telemetry, schema-fit
decisions, and expectation scorecard failures before Granite is reintroduced.

granite-4.0-3b-vision-bf16:v1
  engine: granite
  task: structured_visual_extraction
  model_family: Granite Vision
  base_model: ibm-granite/granite-4.0-3b-vision
  backend: vllm-openai-or-transformers-service
  default_gpu: blackwell-1
  max_images_per_request: 4
  max_image_bytes: 10485760
  source_engine: granite

qwen3-embedding-4b-1536:v1
  engine: text_embedding
  task: embed_text
  model_family: Qwen3-Embedding
  base_model: Qwen/Qwen3-Embedding-4B
  backend: tei-compatible
  default_gpu: rtx3090-0
  output_dimensions: 1536
  pgvector_index: embeddings_text_1536_hnsw_idx
  source_engine: embedding

qwen3-vl-embedding-2b-2048:v1
  engine: visual_embedding
  task: embed_image_or_mixed
  model_family: Qwen3-VL-Embedding
  base_model: Qwen/Qwen3-VL-Embedding-2B
  backend: vllm-embed
  default_gpu: blackwell-1-alternate
  output_dimensions: 2048
  pgvector_index: embeddings_visual_2048_hnsw_idx
  source_engine: embedding
```

## File Structure

Create focused modules rather than appending to existing gateway files:

```text
lib/model_runtime/
  __init__.py
  profiles.py
  settings.py
  http_client.py
  media.py
  redaction.py
  health.py

lib/model_runtime/clients/
  __init__.py
  qwen_vl.py
  granite_vision.py
  text_embeddings.py
  visual_embeddings.py

lib/extraction/gateways/
  __init__.py
  deterministic.py
  qwen_vl.py
  granite_vision.py
  routing.py

lib/search/embeddings/
  __init__.py
  deterministic.py
  text_model.py
  visual_model.py
  validation.py

workers/model_services/
  README.md
  qwen-vllm.example.env
  granite-vision.example.env
  text-embed.example.env
  visual-embed.example.env

tests/unit/model_runtime/
tests/unit/extraction/
tests/unit/search/
tests/integration/model_runtime/
tests/integration/test_phase8_5_model_services.py
tests/fixtures/model_corpus/
tests/fixtures/model_calibration/
```

Compatibility wrappers:

- Keep `lib/extraction/gateway.py` as a re-export/shim during the refactor so existing imports do not break.
- Keep `lib/search/embedding_gateway.py` as a re-export/shim during the refactor so existing imports do not break.

Do not create a vague `utils.py`, `manager.py`, or catch-all `model_service.py`.

## Internal Model Client Contract

Use internal HTTP clients with explicit request/response dataclasses. Do not let route handlers or workers build raw JSON by hand.

Expected generate request shape:

```python
@dataclass(frozen=True)
class VisionGenerateRequest:
    profile_name: str
    prompt_version: str
    prompt: str
    image_inputs: tuple[ModelImageInput, ...]
    response_schema_name: str | None
    max_output_tokens: int
    temperature: float
    timeout_seconds: int
```

Expected generate response shape:

```python
@dataclass(frozen=True)
class VisionGenerateResponse:
    profile_name: str
    model_name: str
    model_version: str
    source_engine: str
    prompt_version: str
    raw_text: str
    normalized_json: dict[str, object]
    confidence_json: dict[str, object]
    input_sha256: tuple[str, ...]
    latency_ms: int
```

Expected embedding request shape:

```python
@dataclass(frozen=True)
class EmbeddingRequest:
    profile_name: str
    inputs: tuple[EmbeddingInput, ...]
    output_dimensions: int
    timeout_seconds: int
```

Expected embedding response shape:

```python
@dataclass(frozen=True)
class EmbeddingResponse:
    profile_name: str
    model_name: str
    model_version: str
    dimensions: int
    vectors: tuple[tuple[float, ...], ...]
    input_sha256: tuple[str, ...]
    latency_ms: int
```

Validation rules:

- Response vector count must equal request input count.
- Every vector dimension must equal the active profile dimension.
- Every vector element must be finite.
- Every image input hash returned by the service must match the request-side hash.
- A generate response that fails schema validation must fail the job or create review-required output; it must not silently promote canonical data.
- Model unavailable, timeout, invalid JSON, invalid vector shape, and unsafe media path are separate failure classes.

## Security Requirements

- Model clients must only call configured base URLs from settings.
- Model clients must not accept user-provided URLs.
- vLLM services must use either local-media paths under a dedicated mount or inline base64. If local media paths are used, the allowed path must be a narrow scratch directory such as `/srv/structura/tmp/model-inputs`.
- Scratch input files must be created with restrictive permissions, content-addressed names, and cleanup after the model call.
- Model service containers must not mount canonical/derived object stores read-write unless required. Prefer read-only model cache plus scratch input.
- Model service responses must be redacted before logging.
- Health snapshots may include service name, profile, model id, status, latency bucket, queue depth, and error class. They must not include prompt, answer, extracted text, image path, or object URI.

## Task 1: Baseline Audit And Fixture Quarantine

**Files:**

- Modify: `lib/search/embedding_gateway.py`
- Modify: `lib/search/embedding_service.py`
- Modify: `lib/extraction/gateway.py`
- Modify: `lib/extraction/classification.py`
- Test: `tests/unit/test_phase8_difficult_documents.py`
- Test: `tests/integration/test_phase8_difficult_documents_integration.py`

- [ ] **Step 1: Write failing tests for fixture-mode provenance**

  Add assertions that deterministic fixture gateways never return `source_engine = qwen` or `source_engine = granite`.

  ```python
  def test_fixture_qwen_route_does_not_claim_qwen_source() -> None:
      result = gateway.extract(source, schema_name="invoice", route_profile="qwen_primary_review_required")
      assert result.route.source_engine == "docling"
      assert result.raw_output_json["qwen_model_invoked"] is False
  ```

- [ ] **Step 2: Run the focused tests and verify failure**

  Run:

  ```bash
  python -m pytest -q tests/unit/test_phase8_difficult_documents.py tests/integration/test_phase8_difficult_documents_integration.py
  ```

  Expected before implementation: at least one test fails if any fixture path still claims Qwen or Granite.

- [ ] **Step 3: Rename fixture profile labels**

  Change deterministic names to explicitly include `fixture` or `deterministic`, for example:

  ```text
  structura-fixture-text-embedding:v1
  structura-fixture-visual-byte-embedding:v1
  docling-heuristic-handwriting-review-route
  ```

  Do not use `qwen`, `granite`, `visual model`, or `local visual model` names for byte-hash fixtures.

- [ ] **Step 4: Add settings gate for fixture mode**

  Add:

  ```python
  model_mode: Literal["fixture", "live", "required"] = "fixture"
  ```

  `live` means call real model services when route/profile requires them and fail safely when unavailable. `required` means no deterministic fallback for model-backed routes.

- [ ] **Step 5: Verify fixture tests pass**

  Run the same focused tests. Expected: pass with honest fixture provenance.

- [ ] **Step 6: Commit**

  ```bash
  git add lib/search lib/extraction tests/unit/test_phase8_difficult_documents.py tests/integration/test_phase8_difficult_documents_integration.py
  git commit -m "Quarantine Phase 8 fixture model provenance"
  ```

## Task 2: Model Profile Registry And Runtime Settings

**Files:**

- Create: `lib/model_runtime/__init__.py`
- Create: `lib/model_runtime/profiles.py`
- Create: `lib/model_runtime/settings.py`
- Modify: `lib/config/settings.py`
- Test: `tests/unit/model_runtime/test_profiles.py`

- [ ] **Step 1: Write profile registry tests**

  Tests must assert:

  - all required profiles exist;
  - text dimensions equal `1536`;
  - visual dimensions equal `2048`;
  - Qwen and Granite source engines are distinct;
  - Blackwell profiles are not assigned to the RTX 3090.

- [ ] **Step 2: Implement `ModelProfile` and registry**

  Use a frozen dataclass:

  ```python
  @dataclass(frozen=True)
  class ModelProfile:
      name: str
      engine: str
      task: str
      base_model: str
      backend: str
      source_engine: str
      output_dimensions: int | None = None
      default_gpu_role: str | None = None
      max_image_bytes: int | None = None
      max_images_per_request: int | None = None
  ```

- [ ] **Step 3: Add settings**

  Add settings for:

  ```text
  STRUCTURA_MODEL_MODE
  STRUCTURA_MODEL_QWEN_URL
  STRUCTURA_MODEL_GRANITE_URL
  STRUCTURA_MODEL_TEXT_EMBED_URL
  STRUCTURA_MODEL_VISUAL_EMBED_URL
  STRUCTURA_QWEN_PROFILE
  STRUCTURA_GRANITE_PROFILE
  STRUCTURA_TEXT_EMBED_PROFILE
  STRUCTURA_VISUAL_EMBED_PROFILE
  STRUCTURA_MODEL_INPUT_SCRATCH_ROOT
  STRUCTURA_MODEL_HTTP_TIMEOUT_SECONDS
  STRUCTURA_MODEL_MAX_IMAGE_BYTES
  ```

- [ ] **Step 4: Run tests**

  ```bash
  python -m pytest -q tests/unit/model_runtime/test_profiles.py
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add lib/model_runtime lib/config/settings.py tests/unit/model_runtime/test_profiles.py
  git commit -m "Add model runtime profile registry"
  ```

## Task 3: Bounded Model HTTP Client And Media Handling

**Files:**

- Create: `lib/model_runtime/http_client.py`
- Create: `lib/model_runtime/media.py`
- Create: `lib/model_runtime/redaction.py`
- Test: `tests/unit/model_runtime/test_http_client.py`
- Test: `tests/unit/model_runtime/test_media.py`
- Modify: `pyproject.toml`
- Modify: `apps/api/requirements.txt`
- Modify: `requirements-dev.lock`

- [ ] **Step 1: Add runtime HTTP dependency**

  Add `httpx` to production dependencies and regenerate lock files with `uv pip compile`.

- [ ] **Step 2: Write tests for URL allow-listing**

  Tests must reject:

  - empty base URL in live/required mode;
  - non-HTTP schemes;
  - user-provided target URLs;
  - redirects to unexpected hosts.

- [ ] **Step 3: Write tests for media scratch safety**

  Tests must assert:

  - scratch paths stay under `STRUCTURA_MODEL_INPUT_SCRATCH_ROOT`;
  - filenames are content-addressed;
  - files are created with restrictive permissions;
  - cleanup removes scratch files after success and failure.

- [ ] **Step 4: Implement `ModelHttpClient`**

  Required behavior:

  - fixed base URL from settings;
  - per-call timeout;
  - response-size limit;
  - JSON parse errors mapped to `ModelProtocolError`;
  - timeout mapped to `ModelTimeoutError`;
  - HTTP 5xx mapped to retryable service errors;
  - HTTP 4xx mapped to non-retryable protocol errors unless explicitly configured.

- [ ] **Step 5: Implement redaction**

  Redaction must replace prompt text, raw output, image paths, object URIs, and data URLs before logging.

- [ ] **Step 6: Run tests**

  ```bash
  python -m pytest -q tests/unit/model_runtime
  ```

- [ ] **Step 7: Commit**

  ```bash
  git add pyproject.toml apps/api/requirements.txt requirements-dev.lock lib/model_runtime tests/unit/model_runtime
  git commit -m "Add bounded internal model HTTP client"
  ```

## Task 4: Qwen3-VL Live Adapter And Service Profile

**Files:**

- Create: `lib/model_runtime/clients/qwen_vl.py`
- Create: `lib/extraction/gateways/qwen_vl.py`
- Modify: `lib/extraction/gateways/routing.py`
- Modify: `compose.yaml`
- Create: `workers/model_services/qwen-vllm.example.env`
- Test: `tests/unit/model_runtime/test_qwen_client.py`
- Test: `tests/integration/test_phase8_5_model_services.py`

- [ ] **Step 1: Write adapter tests with a fake HTTP server**

  Tests must cover:

  - image input is sent as local media/base64 through the internal client;
  - Qwen response is normalized;
  - `source_engine = qwen` only after a successful client response;
  - timeout produces retryable failure;
  - malformed JSON produces non-canonical review-required failure.

- [ ] **Step 2: Implement Qwen client**

  Client responsibilities:

  - build OpenAI-compatible multimodal chat/generate payloads;
  - include `prompt_version`;
  - request structured JSON where the active backend supports it;
  - validate response;
  - return `VisionGenerateResponse`.

- [ ] **Step 3: Implement Qwen extraction gateway**

  The gateway must persist:

  - `source_engine = qwen`;
  - active model profile;
  - model name/version from service response;
  - prompt version;
  - raw output asset reference;
  - normalized JSON;
  - confidence summary;
  - review-required status by default for handwriting routes.

- [ ] **Step 4: Configure Compose service**

  Configure `model-qwen-semantic` for the active
  `qwen3-vl-8b-fp8-semantic:v1` Smart Parse profile. The service must be pinned
  by image tag and digest before release. `latest` is not acceptable.

- [ ] **Step 5: Run tests**

  ```bash
  python -m pytest -q tests/unit/model_runtime/test_qwen_client.py tests/integration/test_phase8_5_model_services.py
  ```

- [ ] **Step 6: Commit**

  ```bash
  git add lib/model_runtime/clients/qwen_vl.py lib/extraction/gateways compose.yaml workers/model_services tests
  git commit -m "Add Qwen VL live model adapter"
  ```

## Task 5: Granite 4.0 3B Vision Adapter And Structured Extraction Route

**Files:**

- Create: `lib/model_runtime/clients/granite_vision.py`
- Create: `lib/extraction/gateways/granite_vision.py`
- Modify: `lib/extraction/gateways/routing.py`
- Modify: `lib/extraction/schema_registry.py`
- Modify: `compose.yaml`
- Create: `workers/model_services/granite-vision.example.env`
- Test: `tests/unit/model_runtime/test_granite_client.py`
- Test: `tests/integration/test_phase8_5_model_services.py`

- [ ] **Step 1: Write structured extraction tests**

  Tests must cover:

  - invoice table extraction uses Granite route when a structured layout signal is present;
  - receipt KVP extraction uses Granite route when table/KVP confidence matters;
  - EOB line-item extraction uses Granite route when tables are present;
  - Qwen semantic planning does not overwrite Granite provenance;
  - Granite response validation failure creates review-required candidates, not canonical facts.

- [ ] **Step 2: Implement Granite client**

  Client responsibilities:

  - send page/crop images plus Docling table/page context;
  - request schema-constrained JSON for `receipt`, `invoice`, and `medical_eob`;
  - return normalized table/KVP evidence with page number and stronger locator fields when present.

- [ ] **Step 3: Implement Granite gateway**

  Required route profiles:

  ```text
  docling_plus_granite_structured
  granite_primary_review_required
  granite_then_qwen_fallback_review_required
  ```

  Granite output must remain candidates until validators and review policy allow promotion.

- [ ] **Step 4: Configure Compose service**

  `model-granite` must run on Blackwell GPU 1 by default and must not share the
  same GPU with the always-on Qwen Smart Parse service.

- [ ] **Step 5: Run tests**

  ```bash
  python -m pytest -q tests/unit/model_runtime/test_granite_client.py tests/integration/test_phase8_5_model_services.py
  ```

- [ ] **Step 6: Commit**

  ```bash
  git add lib/model_runtime/clients/granite_vision.py lib/extraction/gateways compose.yaml workers/model_services tests
  git commit -m "Add Granite Vision structured extraction adapter"
  ```

## Task 6: Text Embedding Service On RTX 3090

**Files:**

- Create: `lib/model_runtime/clients/text_embeddings.py`
- Create: `lib/search/embeddings/text_model.py`
- Modify: `lib/search/embedding_service.py`
- Modify: `lib/search/jobs.py`
- Modify: `compose.yaml`
- Create: `workers/model_services/text-embed.example.env`
- Test: `tests/unit/model_runtime/test_text_embedding_client.py`
- Test: `tests/integration/test_phase8_5_model_services.py`

- [ ] **Step 1: Write tests for TEI-compatible embedding response**

  Tests must assert:

  - output dimensions are exactly `1536`;
  - vector count matches inputs;
  - vectors are finite;
  - model name/version/profile are persisted;
  - deterministic fixture text embeddings are only used in fixture mode.

- [ ] **Step 2: Implement text embedding client**

  Target profile:

  ```text
  Qwen/Qwen3-Embedding-4B
  output_dimensions = 1536
  backend = TEI-compatible
  ```

  Keep 1536 dimensions to preserve existing `embeddings_text_1536_hnsw_idx`.

- [ ] **Step 3: Update embedding service injection**

  `EmbeddingService` should select:

  - deterministic fixture gateway in `STRUCTURA_MODEL_MODE=fixture`;
  - text model HTTP gateway in `live` or `required`.

- [ ] **Step 4: Configure Compose service**

  `model-embed` runs on the RTX 3090 host with model cache mounted from `/srv/structura/models`.

- [ ] **Step 5: Run tests**

  ```bash
  python -m pytest -q tests/unit/model_runtime/test_text_embedding_client.py tests/integration/test_phase8_5_model_services.py
  ```

- [ ] **Step 6: Commit**

  ```bash
  git add lib/model_runtime/clients/text_embeddings.py lib/search compose.yaml workers/model_services tests
  git commit -m "Add live text embedding service adapter"
  ```

## Task 7: True Visual Embedding Service

**Files:**

- Create: `lib/model_runtime/clients/visual_embeddings.py`
- Create: `lib/search/embeddings/visual_model.py`
- Create: `lib/search/embeddings/validation.py`
- Modify: `lib/search/embedding_repository.py`
- Modify: `lib/search/embedding_service.py`
- Modify: `lib/search/jobs.py`
- Modify: `workers/embeddings/worker.py`
- Modify: `compose.yaml`
- Create: `workers/model_services/visual-embed.example.env`
- Test: `tests/unit/model_runtime/test_visual_embedding_client.py`
- Test: `tests/integration/test_phase8_5_model_services.py`

- [ ] **Step 1: Write tests proving image bytes are required**

  Tests must fail if visual embedding is generated from descriptor text alone.

  Required assertions:

  - missing image asset fails the job;
  - changed image bytes change request hash;
  - descriptor-only source cannot produce a live visual vector;
  - response dimensions equal `2048`;
  - profile name starts with `qwen3-vl-embedding`.

- [ ] **Step 2: Implement visual embedding client**

  Initial target profile:

  ```text
  Qwen/Qwen3-VL-Embedding-2B
  output_dimensions = 2048
  backend = vLLM embed or equivalent internal service
  ```

  Keep 2048 dimensions for the live vLLM path because the endpoint returns native
  2048-dimensional vectors and rejects dimensions overrides. Use
  `embeddings_visual_2048_hnsw_idx`.

- [ ] **Step 3: Update visual embedding service path**

  The worker must:

  - load protected image bytes from storage;
  - preprocess or stage image input through `lib/model_runtime/media.py`;
  - call the visual embedding client in live/required mode;
  - validate vector shape;
  - persist model profile, model version, modality, and active row state.

- [ ] **Step 4: Configure scheduled/offline service profile**

  Add `model-vl-embed` as a separate Compose service/profile. It may share Blackwell GPU 1 only when `model-granite` is stopped or when concurrency is proven by benchmark.

- [ ] **Step 5: Run tests**

  ```bash
  python -m pytest -q tests/unit/model_runtime/test_visual_embedding_client.py tests/integration/test_phase8_5_model_services.py
  ```

- [ ] **Step 6: Commit**

  ```bash
  git add lib/model_runtime/clients/visual_embeddings.py lib/search workers/embeddings compose.yaml workers/model_services tests
  git commit -m "Add true visual embedding service adapter"
  ```

## Task 8: Extraction Routing Policy For Docling, Granite, And Qwen

**Files:**

- Create: `lib/extraction/gateways/routing.py`
- Modify: `lib/extraction/classification.py`
- Modify: `lib/extraction/service.py`
- Modify: `lib/extraction/source_repository.py`
- Modify: `lib/extraction/normalization.py`
- Test: `tests/unit/test_phase4_extraction.py`
- Test: `tests/unit/test_phase8_difficult_documents.py`
- Test: `tests/integration/test_phase8_5_model_services.py`

- [ ] **Step 1: Write routing tests**

  Required cases:

  ```text
  digital-native simple invoice -> docling_plus_granite_structured optional, deterministic allowed only in fixture
  structured bill with tables -> docling_plus_granite_structured
  handwriting-heavy page -> Qwen3-VL-8B FP8 smart semantic routing, review-required when uncertain
  degraded low-text page -> Qwen3-VL-8B FP8 smart semantic routing or visual review route
  Granite validation needs_review -> review-required, no hidden Qwen escalation
  Granite recoverable semantic issue -> review-required or classified skip, no Qwen escalation
  ```

- [ ] **Step 2: Implement routing policy**

  Rules:

  - Docling remains canonical structural parse.
  - Granite is preferred for tables, KVPs, line items, bills, receipts, invoices, and EOBs with layout complexity.
  - Qwen3-VL-8B FP8 provides semantic planning/routing and may not create canonical facts.
  - No separate Qwen escalation services run in the active runtime.
  - Model-derived uncertain output remains review-required.

- [ ] **Step 3: Persist route trace**

  Every extraction run must persist:

  - route profile;
  - source engine;
  - model profile;
  - prompt version;
  - raw output asset;
  - validation report;
  - review-required reason.

- [ ] **Step 4: Run regression tests**

  ```bash
  python -m pytest -q tests/unit/test_phase4_extraction.py tests/unit/test_phase8_difficult_documents.py tests/integration/test_phase8_5_model_services.py
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add lib/extraction tests/unit tests/integration/test_phase8_5_model_services.py
  git commit -m "Route extraction through Docling Granite and Qwen"
  ```

## Task 9: Model Health, Admin Visibility, And Redacted Observability

**Files:**

- Create: `lib/model_runtime/health.py`
- Modify: `lib/jobs/service.py`
- Modify: `apps/api/structura_api/routes_admin.py`
- Modify: `workers/embeddings/worker.py`
- Modify: `workers/extraction/worker.py`
- Test: `tests/integration/test_phase8_5_model_services.py`

- [ ] **Step 1: Write health snapshot tests**

  Tests must assert health reports include:

  - configured profile;
  - fixture/live/required mode;
  - service availability;
  - last success timestamp;
  - timeout/error counts;
  - queue depth and oldest job age where relevant.

  Tests must assert health reports exclude:

  - prompt text;
  - raw model output;
  - document text;
  - image path;
  - storage URI.

- [ ] **Step 2: Implement model health snapshots**

  Record service health for:

  ```text
  model-qwen-semantic
  model-granite
  model-embed
  model-vl-embed
  worker-embeddings
  worker-visual-embeddings
  worker-extraction
  ```

- [ ] **Step 3: Wire admin route**

  Admin/service health must show model unavailable and fixture mode clearly. It must not imply model-backed readiness when placeholders are running.

- [ ] **Step 4: Run tests**

  ```bash
  python -m pytest -q tests/integration/test_phase8_5_model_services.py
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add lib/model_runtime/health.py lib/jobs apps/api workers tests
  git commit -m "Expose redacted model service health"
  ```

## Task 10: Compose Profiles, Model Images, And GPU Placement

**Files:**

- Modify: `compose.yaml`
- Create: `infrastructure/models/README.md`
- Create: `infrastructure/models/qwen-vllm.env.example`
- Create: `infrastructure/models/granite-vision.env.example`
- Create: `infrastructure/models/text-embed.env.example`
- Create: `infrastructure/models/visual-embed.env.example`
- Modify: `README.md`
- Test: `tests/unit/test_compose_model_profiles.py`

- [ ] **Step 1: Write static Compose tests**

  Assert:

  - model ports bind to `127.0.0.1` by default;
  - model services mount `/srv/structura/models`;
  - Qwen and Granite default to different GPU ids;
  - `model-vl-embed` is not always-on with Granite unless an explicit profile is selected;
  - placeholder image mode is visibly named placeholder.

- [ ] **Step 2: Update Compose profiles**

  Profiles:

  ```text
  models-placeholder
  models-live
  qwen-live
  granite-live
  text-embed-live
  visual-embed-live
  ```

  Keep deterministic tests able to run without GPU.

- [ ] **Step 3: Document image pinning policy**

  Model images must be pinned by tag and digest. Community or experimental images, including cu130/SM120 forks, must be explicitly labeled experimental until live benchmark evidence is recorded.

- [ ] **Step 4: Run Compose validation**

  ```bash
  docker compose --profile models-placeholder config -q
  docker compose --profile models-live config -q
  docker compose --profile visual-embed-live config -q
  ```

- [ ] **Step 5: Commit**

  ```bash
  git add compose.yaml infrastructure/models README.md tests/unit/test_compose_model_profiles.py
  git commit -m "Define live model service compose profiles"
  ```

## Task 11: Model-Backed Golden Corpus And Release Evidence

**Files:**

- Modify: `scripts/run_golden_corpus.py`
- Create: `scripts/run_model_corpus.py`
- Create: `tests/fixtures/model_corpus/README.md`
- Create: `tests/fixtures/model_corpus/phase8_5_model_manifest.example.json`
- Modify: `Makefile`
- Modify: `.github/workflows/ci.yml`
- Test: `tests/unit/test_model_corpus_runner.py`

- [ ] **Step 1: Write corpus runner tests**

  Tests must assert:

  - deterministic corpus still runs without model services;
  - `--require-model-backed` fails on fixture manifests;
  - Qwen, Granite, text embedding, and visual embedding evidence sections are required for model-backed manifests;
  - thresholds are enforced.

- [ ] **Step 2: Implement model corpus runner**

  Required metrics:

  ```text
  qwen_handwriting_route_success_rate
  qwen_review_required_rate
  granite_table_structure_score
  granite_kvp_exact_match
  text_embedding_hit_rate_at_k
  visual_embedding_hit_rate_at_k
  hybrid_hit_rate_at_k
  provenance_truth_rate
  ```

- [ ] **Step 3: Add Makefile targets**

  ```make
  golden-corpus:
    $(PYTHON) scripts/run_golden_corpus.py

  model-corpus:
    $(PYTHON) scripts/run_model_corpus.py --manifest tests/fixtures/model_corpus/phase8_5_model_manifest.example.json
  ```

- [ ] **Step 4: CI behavior**

  CI should keep deterministic corpus required. Model-backed corpus may be manual or self-hosted GPU-only until model services are available in CI.

- [ ] **Step 5: Commit**

  ```bash
  git add scripts Makefile .github/workflows/ci.yml tests/fixtures/model_corpus tests/unit/test_model_corpus_runner.py
  git commit -m "Add Phase 8.5 model-backed corpus gate"
  ```

## Task 12: GPU Node Live Validation Gate

**Files:**

- Create: `scripts/gpu/phase8_5_model_smoke.sh`
- Create: `docs/model-runtime/phase8_5_gpu_validation.md`
- Modify: `.github/workflows/gpu-live-smoke.yml`
- Modify: `README.md`

- [ ] **Step 1: Create GPU smoke script**

  Script must validate:

  - GPU inventory;
  - model services healthy;
  - Qwen sample image request succeeds;
  - Granite structured sample request succeeds;
  - text embedding request returns 1536 dimensions;
  - visual embedding request returns 2048 dimensions;
  - live Phase 8 E2E still passes;
  - model-backed corpus thresholds pass.

- [ ] **Step 2: Add workflow/manual gate**

  Add an optional self-hosted workflow dispatch that runs Phase 8.5 live model smoke against the GPU node. Do not make public GitHub-hosted runners download private documents or model artifacts.

- [ ] **Step 3: Document GPU commands**

  Document:

  ```bash
  ssh -i /Users/brennanconley/vibecode/infx/ubuntu24_ed25519 bgconley@10.25.0.50
  cd /tank/repos/structura
  git pull --ff-only
  docker compose --profile models-live --profile visual-embed-live up -d model-qwen-semantic model-vl-embed
  docker compose --profile text-embed-live up -d model-embed
  bash scripts/gpu/phase8_5_model_smoke.sh
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add scripts/gpu docs/model-runtime .github/workflows/gpu-live-smoke.yml README.md
  git commit -m "Add Phase 8.5 GPU model validation gate"
  ```

## Task 13: Documentation, ADR, And Phase 9 Handoff

**Files:**

- Create: `docs/adr/0004-phase-8-5-local-model-runtime.md`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `STRUCTURA_IMPLEMENTATION_PLAN.md`
- Modify: `STRUCTURA_PHASE_9_IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Write ADR**

  ADR must record:

  - Qwen semantic planning and Qwen vision fallback are default priorities;
  - Blackwell GPU 0 runs Qwen;
  - Granite is excluded from the default live runtime and is available through explicit rollback/comparison profiles only;
  - RTX 3090 runs text embeddings;
  - visual embedding is real and part of the default live model gate;
  - fixture mode is test-only;
  - provenance must reflect actual adapter invocation.

- [ ] **Step 2: Update Phase 9 prerequisites**

  Phase 9 must require Phase 8.5 gates before analysis is enabled.

- [ ] **Step 3: Update README**

  README must distinguish:

  - deterministic fixture mode;
  - model placeholder mode;
  - live model-backed mode;
  - model-backed release gates.

- [ ] **Step 4: Update AGENTS.md**

  Add that Phase 8.5 is the current prerequisite before Phase 9 and that fake visual/Qwen behavior must not be reintroduced.

- [ ] **Step 5: Commit**

  ```bash
  git add docs/adr README.md AGENTS.md STRUCTURA_IMPLEMENTATION_PLAN.md STRUCTURA_PHASE_9_IMPLEMENTATION_PLAN.md
  git commit -m "Document Phase 8.5 model runtime decisions"
  ```

## Phase 8.5 Gate

Phase 8.5 is complete only when all of the following are true, together with the completion plan's current G3 criteria:

- Fixture gateways are explicitly named as fixtures and cannot claim Qwen/Granite provenance.
- Default ingest uses the selected Oxcart Qwen3.8-27B BF16 profile with original page images and available native text under ADR 0009. Full searchable structure, source/evidence verification and review work end to end with Docling disabled. Parse, extraction and planning contracts preserve separate origins; model transcription cannot certify itself.
- Provider-neutral parse/version migrations, generation-aware indexes and scoped rollback preserve genuine historical artifacts, evidence navigation and later human corrections. Parser recovery works without Docling; full archive restore follows the later OPS-02 release gate.
- No hidden second-pass Qwen escalation runs from validation/review policy.
- Document-quality ambiguity routes to review states, not job failure.
- Runtime/system failures are the only `pipeline_failed` cases.
- Uncertainty remains on review, skip, or abstention paths; separate Qwen
  rescue/escalation is not part of the active runtime.
- Private corpus standard mode does not secretly run High Quality.
- Current 27B calls and historical/canary/comparison profiles persist truthful actual-adapter identity; existing 8B rows are not relabeled and 27B cannot bypass model-backed review through an old allowlist.
- Granite 4.0 3B Vision live adapter is optional rollback/comparison infrastructure and is not required by the default live runtime.
- Text embeddings use a real embedding service in live mode and persist 1536-dimensional vectors.
- Visual embeddings use a real visual embedding service in live mode and persist 2048-dimensional vectors generated from image inputs.
- Deterministic CI remains green without GPU services.
- Authenticated real-adapter validation proves 27B text/image/structured behavior and the selected text/visual retrieval endpoints. Concurrent ingestion/search and other Oxcart-client impact are measured against bounded admission budgets.
- Model-backed golden corpus evidence exists for handwriting, structured tables/KVPs, text retrieval, visual retrieval, and hybrid retrieval.
- Model service health is visible without leaking private content.
- Phase 9 plan is updated to depend on Phase 8.5.

Historical measured evidence at commit `e8bb26b` proves the two-document
model-backed UAT pipeline on the GPU node, but it is not a full release-gold
proof. Reports
`/srv/structura/objects/exports/phase85-runs/uat-e8bb26b/20260613T053814Z-uat-e8bb26b-pass-1-report.json`
and
`/srv/structura/objects/exports/phase85-runs/uat-e8bb26b/20260613T053814Z-uat-e8bb26b-pass-2-report.json`
passed hard correctness, operational SLO, lineage, required summary,
repeatability, safe-outcome, planner, evidence, and visual-plan checks. The
same reports have `goldCorpusQuality = not_evaluated` because the private
two-document holdout manifest does not include `goldMetrics` and
`goldThresholds`; strict `--require-gold` release evidence still requires a
gold-annotated private manifest.

Required deterministic checks:

```bash
python -m ruff check .
python -m ruff format --check .
python scripts/validate_contracts.py
python -m pyright --pythonpath "$(command -v python)" apps lib workers scripts
python -m mypy apps/api lib workers scripts
python -m pytest -q tests/unit
python scripts/run_integration_tests.py
python scripts/run_golden_corpus.py
python -m bandit -r apps lib workers scripts
semgrep scan --config auto --exclude archive
docker compose config -q
docker compose --profile extraction --profile search --profile relationships --profile automation --profile visual --profile models-placeholder config -q
```

Historical GPU live command example — superseded by the Oxcart 27B integration and Blackbird embedding strategy. Adapt managed scripts and profile/authentication/report contracts first; do not run this example to recreate shared inference. Current required live checks are X-01/X-06/X-07/X-08 and the completion execution strategy.

```bash
docker compose --profile models-live --profile visual-embed-live up -d model-qwen-semantic model-vl-embed
docker compose --profile text-embed-live up -d model-embed
bash scripts/gpu/phase8_5_model_smoke.sh
python scripts/run_model_corpus.py --require-model-backed --manifest tests/fixtures/model_corpus/phase8_5_model_manifest.json
```

Run ad hoc private-document diagnostics separately from the release corpus gate:

```bash
python scripts/gpu/run_phase8_5_private_corpus.py --pdf /path/to/private.pdf
```

Required browser checks:

```bash
docker run --rm \
  -e STRUCTURA_E2E_LIVE=1 \
  -e STRUCTURA_E2E_WEB_URL=http://10.25.0.50:13000 \
  -v "$PWD":/workspace \
  --mount type=volume,src=structura-ci-node-modules,dst=/workspace/node_modules \
  --mount type=volume,src=structura-ci-web-node-modules,dst=/workspace/apps/web/node_modules \
  -w /workspace \
  mcr.microsoft.com/playwright:v1.59.1-noble \
  sh -lc "npm ci && npx playwright test tests/e2e/phase1-live.spec.ts tests/e2e/phase2-live.spec.ts tests/e2e/phase3-live.spec.ts tests/e2e/phase4-live.spec.ts tests/e2e/phase5-live.spec.ts tests/e2e/phase6-live.spec.ts tests/e2e/phase7-live.spec.ts tests/e2e/phase8-live.spec.ts --workers=1"
```

## Stop Point

After Phase 8.5 is implemented and verified, stop and report:

- model profiles implemented;
- services and GPU placement used;
- selected 27B ingestion, text embedding and visual embedding evidence; optional historical/comparison results labeled separately;
- fixture-vs-live behavior;
- model-backed corpus results;
- GPU validation commands and results;
- known limitations before Phase 9.

Do not continue into Phase 9 until the user explicitly approves the next phase.
