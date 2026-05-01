from __future__ import annotations

from dataclasses import dataclass

from lib.config import get_settings
from lib.model_runtime.profiles import ModelProfile, get_model_profile


@dataclass(frozen=True)
class ConfiguredModelProfiles:
    qwen_semantic: ModelProfile
    granite: ModelProfile
    text_embedding: ModelProfile
    visual_embedding: ModelProfile


def configured_model_profiles(
    *,
    qwen_semantic_profile: str | None = None,
    granite_profile: str | None = None,
    text_embed_profile: str | None = None,
    visual_embed_profile: str | None = None,
) -> ConfiguredModelProfiles:
    settings = get_settings()
    return ConfiguredModelProfiles(
        qwen_semantic=get_model_profile(qwen_semantic_profile or settings.qwen_semantic_profile),
        granite=get_model_profile(granite_profile or settings.granite_profile),
        text_embedding=get_model_profile(text_embed_profile or settings.text_embed_profile),
        visual_embedding=get_model_profile(visual_embed_profile or settings.visual_embed_profile),
    )
