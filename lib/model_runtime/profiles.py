from __future__ import annotations

from dataclasses import dataclass

QWEN_VL_PROFILE = "qwen3-vl-8b-instruct-nvfp4-local:v1"
QWEN_HISTORICAL_SEMANTIC_2B_PROFILE = "qwen3-vl-2b-semantic:v1"
QWEN_HISTORICAL_SEMANTIC_4B_PROFILE = "qwen3-vl-4b-semantic:v1"
QWEN_SEMANTIC_PROFILE = "qwen3-vl-8b-fp8-semantic:v1"
QWEN_SEMANTIC_HQ_PROFILE = "qwen3-vl-8b-semantic-hq:v1"
GRANITE_VISION_PROFILE = "granite-4.0-3b-vision-bf16:v1"
TEXT_EMBED_PROFILE = "qwen3-embedding-4b-1536:v1"
VISUAL_EMBED_PROFILE = "qwen3-vl-embedding-2b-2048:v1"


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
    max_model_len: int | None = None
    pgvector_index: str | None = None
    visual_token_spatial_compression: int | None = None
    visual_token_min_per_image: int | None = None
    visual_token_max_per_image: int | None = None


_PROFILES: dict[str, ModelProfile] = {
    QWEN_VL_PROFILE: ModelProfile(
        name=QWEN_VL_PROFILE,
        engine="qwen",
        task="multimodal_generate",
        base_model="Qwen/Qwen3-VL-8B-Instruct",
        backend="vllm-openai",
        source_engine="qwen3_vl_8b",
        default_gpu_role="blackwell-0",
        max_image_bytes=10 * 1024 * 1024,
        max_images_per_request=1,
        max_model_len=32768,
    ),
    QWEN_SEMANTIC_PROFILE: ModelProfile(
        name=QWEN_SEMANTIC_PROFILE,
        engine="qwen",
        task="semantic_annotation",
        base_model="Qwen/Qwen3-VL-8B-Instruct-FP8",
        backend="vllm-openai",
        source_engine="qwen3_vl_8b",
        default_gpu_role="blackwell-0",
        max_image_bytes=10 * 1024 * 1024,
        max_images_per_request=4,
        max_model_len=32768,
        visual_token_spatial_compression=32,
        visual_token_min_per_image=256,
        visual_token_max_per_image=2560,
    ),
    QWEN_HISTORICAL_SEMANTIC_4B_PROFILE: ModelProfile(
        name=QWEN_HISTORICAL_SEMANTIC_4B_PROFILE,
        engine="qwen",
        task="semantic_annotation_historical",
        base_model="Qwen/Qwen3-VL-4B-Instruct",
        backend="vllm-openai",
        source_engine="qwen3_vl_4b",
        default_gpu_role="historical",
        max_image_bytes=10 * 1024 * 1024,
        max_images_per_request=4,
        max_model_len=32768,
        visual_token_spatial_compression=32,
        visual_token_min_per_image=256,
        visual_token_max_per_image=2560,
    ),
    QWEN_HISTORICAL_SEMANTIC_2B_PROFILE: ModelProfile(
        name=QWEN_HISTORICAL_SEMANTIC_2B_PROFILE,
        engine="qwen",
        task="semantic_annotation_historical",
        base_model="Qwen/Qwen3-VL-2B-Instruct",
        backend="vllm-openai",
        source_engine="qwen3_vl_2b",
        default_gpu_role="historical",
        max_image_bytes=10 * 1024 * 1024,
        max_images_per_request=4,
        max_model_len=32768,
    ),
    QWEN_SEMANTIC_HQ_PROFILE: ModelProfile(
        name=QWEN_SEMANTIC_HQ_PROFILE,
        engine="qwen",
        task="semantic_annotation_high_quality",
        base_model="Qwen/Qwen3-VL-8B-Instruct",
        backend="vllm-openai",
        source_engine="qwen3_vl_8b",
        default_gpu_role="blackwell-0-high-quality",
        max_image_bytes=10 * 1024 * 1024,
        max_images_per_request=1,
        max_model_len=32768,
    ),
    GRANITE_VISION_PROFILE: ModelProfile(
        name=GRANITE_VISION_PROFILE,
        engine="granite",
        task="structured_visual_extraction",
        base_model="ibm-granite/granite-4.0-3b-vision",
        backend="vllm-openai-or-transformers-service",
        source_engine="granite_vision_3b",
        default_gpu_role="blackwell-1",
        max_image_bytes=10 * 1024 * 1024,
        max_images_per_request=4,
    ),
    TEXT_EMBED_PROFILE: ModelProfile(
        name=TEXT_EMBED_PROFILE,
        engine="text_embedding",
        task="embed_text",
        base_model="Qwen/Qwen3-Embedding-4B",
        backend="tei-compatible",
        source_engine="system",
        output_dimensions=1536,
        default_gpu_role="rtx3090-0",
        pgvector_index="embeddings_text_1536_hnsw_idx",
    ),
    VISUAL_EMBED_PROFILE: ModelProfile(
        name=VISUAL_EMBED_PROFILE,
        engine="visual_embedding",
        task="embed_image_or_mixed",
        base_model="Qwen/Qwen3-VL-Embedding-2B",
        backend="vllm-embed",
        source_engine="system",
        output_dimensions=2048,
        default_gpu_role="blackwell-1-alternate",
        max_image_bytes=10 * 1024 * 1024,
        max_images_per_request=8,
        pgvector_index="embeddings_visual_2048_hnsw_idx",
    ),
}


def required_live_profile_names() -> tuple[str, ...]:
    return (
        QWEN_SEMANTIC_PROFILE,
        GRANITE_VISION_PROFILE,
        TEXT_EMBED_PROFILE,
        VISUAL_EMBED_PROFILE,
    )


def get_model_profile(name: str) -> ModelProfile:
    try:
        return _PROFILES[name]
    except KeyError as exc:
        raise KeyError(f"Unknown model profile: {name}") from exc
