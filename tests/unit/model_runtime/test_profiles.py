from __future__ import annotations

import pytest

from lib.model_runtime.profiles import (
    GRANITE_VISION_PROFILE,
    QWEN_SEMANTIC_HQ_PROFILE,
    QWEN_SEMANTIC_PROFILE,
    QWEN_VL_PROFILE,
    TEXT_EMBED_PROFILE,
    VISUAL_EMBED_PROFILE,
    ModelProfile,
    get_model_profile,
    required_live_profile_names,
)
from lib.model_runtime.settings import configured_model_profiles


def test_phase8_5_required_live_profiles_are_registered() -> None:
    assert required_live_profile_names() == (
        QWEN_VL_PROFILE,
        QWEN_SEMANTIC_PROFILE,
        QWEN_SEMANTIC_HQ_PROFILE,
        GRANITE_VISION_PROFILE,
        TEXT_EMBED_PROFILE,
        VISUAL_EMBED_PROFILE,
    )

    profiles = [get_model_profile(name) for name in required_live_profile_names()]

    assert all(isinstance(profile, ModelProfile) for profile in profiles)


def test_qwen_semantic_profiles_distinguish_smart_and_high_quality_modes() -> None:
    smart = get_model_profile(QWEN_SEMANTIC_PROFILE)
    high_quality = get_model_profile(QWEN_SEMANTIC_HQ_PROFILE)

    assert smart.base_model == "Qwen/Qwen3-VL-2B-Instruct"
    assert smart.source_engine == "qwen3_vl_2b"
    assert smart.default_gpu_role == "blackwell-0"
    assert high_quality.base_model == "Qwen/Qwen3-VL-8B-Instruct"
    assert high_quality.source_engine == "qwen3_vl_8b"
    assert high_quality.default_gpu_role == "blackwell-0-high-quality"


def test_qwen_and_granite_profiles_have_distinct_truthful_source_engines() -> None:
    qwen = get_model_profile(QWEN_VL_PROFILE)
    granite = get_model_profile(GRANITE_VISION_PROFILE)

    assert qwen.source_engine == "qwen3_vl_8b"
    assert granite.source_engine == "granite_vision_3b"
    assert qwen.source_engine != granite.source_engine
    assert qwen.default_gpu_role == "blackwell-0"
    assert granite.default_gpu_role == "blackwell-1"


def test_embedding_profiles_preserve_existing_pgvector_dimensions_and_gpu_placement() -> None:
    text = get_model_profile(TEXT_EMBED_PROFILE)
    visual = get_model_profile(VISUAL_EMBED_PROFILE)

    assert text.output_dimensions == 1536
    assert text.pgvector_index == "embeddings_text_1536_hnsw_idx"
    assert text.default_gpu_role == "rtx3090-0"
    assert visual.output_dimensions == 1024
    assert visual.pgvector_index == "embeddings_visual_1024_hnsw_idx"
    assert visual.default_gpu_role == "blackwell-1-alternate"


def test_unknown_profile_fails_closed() -> None:
    with pytest.raises(KeyError, match="Unknown model profile"):
        get_model_profile("qwen3-vl-unreviewed-floating-latest")


def test_configured_model_profiles_resolve_settings_values() -> None:
    profiles = configured_model_profiles(
        qwen_profile=QWEN_VL_PROFILE,
        granite_profile=GRANITE_VISION_PROFILE,
        text_embed_profile=TEXT_EMBED_PROFILE,
        visual_embed_profile=VISUAL_EMBED_PROFILE,
    )

    assert profiles.qwen.name == QWEN_VL_PROFILE
    assert profiles.granite.name == GRANITE_VISION_PROFILE
    assert profiles.text_embedding.output_dimensions == 1536
    assert profiles.visual_embedding.output_dimensions == 1024
