# Structura Phase 8.5 Model And Embedding Services Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Phase 8 fixture/fake model behavior with real local model services for the intended Docling -> Qwen3-VL-8B-Instruct-FP8 -> Granite Vision pipeline, before Phase 9 analysis begins.

**Architecture:** Phase 8.5 inserts a model-runtime foundation between Phase 8 and Phase 9. API, workers, and services keep deterministic fixture adapters for tests, but production/live GPU mode must use explicit HTTP model adapters with truthful provenance, bounded inputs, dimension validation, and model-backed golden evidence.

**Tech Stack:** FastAPI/Python workers, PostgreSQL/pgvector, Docker Compose profiles, vLLM/OpenAI-compatible model APIs, TEI-compatible embedding APIs, Qwen3-VL-8B-Instruct-FP8 semantic annotation, Granite 4.0 3B Vision, Qwen3-Embedding, Qwen3-VL-Embedding, RTX PRO 4000 Blackwell SM120 GPUs, RTX 3090.

## Phase 8.5 Realignment

Canonical default pipeline:

```text
Docling physical parse
-> Qwen3-VL-8B-Instruct-FP8 smart semantic annotation
-> Granite 4.0 3B Vision targeted extraction
-> validators / provenance / review policy
-> canonical facts + evidence/search layer
```

User-selectable modes:

- `smart`: default Qwen3-VL-8B-Instruct-FP8 semantic pass using the same
  semantic manifest contract and Docling-grounded harness as the original 2B/4B
  path.
- `review_only`: uncertain output routes to review without hidden automatic
  escalation.
- `high_quality` / `rescue_permitted`: deferred legacy intent fields. They must
  not silently start a separate second-pass Qwen service unless a future explicit
  evaluation re-enables that path.

Persist these intent fields in semantic job payloads and audit-visible job data:

- `semantic_quality_mode`: `smart` or `high_quality`
- `allow_8b_rescue`: `true` or `false`
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
- Granite 4.0 3B Vision is a first-class requirement for structured documents, because bills, invoices, EOBs, statements, forms, tables, and charts need layout-preserving extraction for later querying and analysis.
- Phase 9 analysis must not be built on fake model outputs, unverified structure extraction, or undocumented model service assumptions.

Phase 8.5 is therefore a mandatory stop point before Phase 9.

## Final Model Priority Decision

Treat Qwen3-VL-8B-Instruct-FP8 semantic annotation and Granite 4.0 3B Vision as
the default implementation priorities. The separate legacy `model-qwen` HQ/rescue
service remains disabled/deferred; default Smart Parse uses the FP8 8B semantic
service directly.

Qwen3-VL-8B-Instruct-FP8 owns:

- smart semantic annotation over Docling-grounded pages and regions;
- bounded routing metadata for Granite;
- ambiguity flags and review hints that do not become canonical facts.

Deferred HQ/rescue paths own no active default runtime until re-evaluated.

Granite 4.0 3B Vision owns:

- layout-sensitive structured extraction;
- tables;
- charts;
- forms;
- semantic key-value pairs;
- invoices, bills, receipts, EOBs, statements, and other structure-heavy household documents.

Text embeddings own:

- default text-heavy retrieval;
- chunk and document retrieval;
- filter-aware semantic search from Phase 5.

Visual embeddings own:

- selective image/page retrieval for low-text, handwriting, degraded, image-heavy, or layout-distinctive pages;
- visual search candidate recall, not canonical fact authority.

## Research Evidence Summary

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
- Do not auto-run Qwen3-VL 8B during default ingest, default private corpus validation, or ordinary `needs_review`.
- Do not treat low confidence, high-risk document family, or human-review policy as `pipeline_failed`.
- Do not conflate human review required with extraction failure.
- Do not let Qwen annotations become canonical facts or Granite candidates bypass validators/review policy.
- Do not create repeated rescue loops or unbounded semantic/Granite fanout.
- Do not log raw document text, image bytes, prompts, responses, object paths, presigned URLs, or model input file paths.
- Model services must not fetch arbitrary external URLs. Pass sanitized local files mounted under a narrow allowed directory or base64 payloads through internal-only APIs.
- Model service ports stay bound to `127.0.0.1` or Docker-internal networking unless a later operations ADR explicitly exposes them.
- Every model call must have timeout, max input size, retry/dead-letter semantics, model profile metadata, and redacted error behavior.

## Tightened Execution Order

1. Lock contracts and tests around explicit Qwen3-VL 8B intent.
2. Persist semantic intent fields in semantic and Granite extraction job payloads.
3. Keep uncertainty on the review/skip path; do not introduce a default rescue
   policy or hidden second Qwen pass.
4. Enforce Smart Parse and Granite job dedupe/caps in
   `lib/semantic_annotations/jobs.py` and the planner.
5. Fix `scripts/gpu/run_phase8_5_private_corpus.py` so standard mode is Docling
   -> smart semantic -> Granite -> validation -> visual embedding.
6. Keep standard/private/resident corpus runs on the Smart Parse path unless a
   future explicit plan reintroduces separate escalation.
7. Keep Viewer/API controls limited to Smart Parse diagnostics in the active
   runtime.
8. Run standard private corpus, Qwen3-VL-8B FP8 semantic JSON, Granite targeted extraction,
   visual embedding, and CI gates as separate evidence streams.
9. Before full corpus reruns after semantic changes, run the semantic-only canary
   (`scripts/gpu/run_phase8_5_semantic_canary.py`) to inspect Docling audit
   anchors, Qwen document-family votes, image fan-in/fallback telemetry, and
   target-schema fit decisions without enqueuing Granite.

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

Canonical GPU placement:

```text
P620 Blackwell node, GPU 0:
  model-qwen-semantic
  Qwen3-VL-8B-Instruct-FP8 smart semantic annotation.

P620 Blackwell node, GPU 0 deferred explicit user-selected/user-permitted profile:
  model-qwen
  Disabled/deferred legacy high-quality or one-pass rescue profile.

P620 Blackwell node, GPU 1:
  model-granite
  Granite 4.0 3B Vision.

P620 Blackwell node, GPU 1 alternate scheduled profile:
  model-vl-embed
  Qwen3-VL-Embedding-2B at native 2048 dimensions; benchmark 8B before promotion.

RTX 3090 node:
  model-embed
  Qwen3-Embedding-4B via TEI-compatible serving at 1536 dimensions.
```

Do not assume two 24 GB Blackwell cards can be treated as one 48 GB pool. Use one major service per card unless tensor parallelism is separately benchmarked and documented.

Default live profiles:

```text
STRUCTURA_MODEL_MODE=live
STRUCTURA_QWEN_SEMANTIC_PROFILE=qwen3-vl-8b-fp8-semantic:v1
STRUCTURA_QWEN_PROFILE=qwen3-vl-8b-instruct-nvfp4-local:v1
STRUCTURA_GRANITE_PROFILE=granite-4.0-3b-vision-bf16:v1
STRUCTURA_TEXT_EMBED_PROFILE=qwen3-embedding-4b-1536:v1
STRUCTURA_VISUAL_EMBED_PROFILE=qwen3-vl-embedding-2b-2048:v1
```

Test/CI fixture profile:

```text
STRUCTURA_MODEL_MODE=fixture
```

Fixture mode is allowed in unit tests, deterministic CI, and local no-GPU development. Fixture mode is not acceptable for Phase 8.5 live gate completion.

## Model Profile Registry

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

qwen3-vl-8b-semantic-hq:v1
  engine: qwen
  task: semantic_annotation_high_quality
  model_family: Qwen3-VL
  base_model: Qwen/Qwen3-VL-8B-Instruct
  backend: vllm-openai
  default_gpu: blackwell-0-high-quality
  max_images_per_request: 1
  max_image_bytes: 10485760
  max_model_len: 32768
  source_engine: qwen3_vl_8b

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

  Replace placeholder `model-qwen` with a model profile that can run one of:

  ```text
  qwen3-vl-8b-instruct-nvfp4-local:v1
  qwen3-vl-8b-instruct-int4-local:v1
  qwen3-vl-8b-instruct-bf16:v1, only if memory tests pass
  ```

  The service must be pinned by image tag and digest before release. `latest` is not acceptable.

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

  `model-granite` must run on Blackwell GPU 1 by default and must not share the same GPU with always-on `model-qwen`.

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
  Granite recoverable semantic issue + future re-enabled rescue policy -> explicit separate rescue only
  ```

- [ ] **Step 2: Implement routing policy**

  Rules:

  - Docling remains canonical structural parse.
  - Granite is preferred for tables, KVPs, line items, bills, receipts, invoices, and EOBs with layout complexity.
  - Qwen3-VL-8B FP8 provides semantic planning/routing and may not create canonical facts.
  - Separate rescue/HQ services remain disabled/deferred unless re-enabled by a future explicit plan.
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
  model-qwen
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
  docker compose --profile models-live up -d model-qwen-semantic model-granite model-embed
  docker compose --profile visual-embed-live up -d model-vl-embed
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

  - Qwen and Granite are equal priorities;
  - Blackwell GPU 0 runs Qwen;
  - Blackwell GPU 1 runs Granite by default;
  - RTX 3090 runs text embeddings;
  - visual embedding is real but queued/offline until concurrency with Granite is proven;
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

Phase 8.5 is complete only when all of the following are true:

- Fixture gateways are explicitly named as fixtures and cannot claim Qwen/Granite provenance.
- Default ingest uses Docling -> Qwen3-VL-8B-Instruct-FP8 -> Granite.
- No hidden second-pass Qwen escalation runs from validation/review policy.
- Document-quality ambiguity routes to review states, not job failure.
- Runtime/system failures are the only `pipeline_failed` cases.
- Rescue is user-permitted, bounded, deduped, and never loops.
- Private corpus standard mode does not secretly run High Quality.
- Qwen3-VL-8B FP8, historical/canary Qwen profiles, and Granite live adapters persist truthful provenance only when invoked.
- Granite 4.0 3B Vision live adapter is implemented, invoked, and persists truthful Granite provenance.
- Text embeddings use a real embedding service in live mode and persist 1536-dimensional vectors.
- Visual embeddings use a real visual embedding service in live mode and persist 2048-dimensional vectors generated from image inputs.
- Deterministic CI remains green without GPU services.
- GPU live validation proves model services respond on the canonical GPU node.
- Model-backed golden corpus evidence exists for handwriting, structured tables/KVPs, text retrieval, visual retrieval, and hybrid retrieval.
- Model service health is visible without leaking private content.
- Phase 9 plan is updated to depend on Phase 8.5.

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

Required GPU live checks:

```bash
docker compose --profile models-live up -d model-qwen-semantic model-granite model-embed
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
- Qwen, Granite, text embedding, and visual embedding evidence;
- fixture-vs-live behavior;
- model-backed corpus results;
- GPU validation commands and results;
- known limitations before Phase 9.

Do not continue into Phase 9 until the user explicitly approves the next phase.
