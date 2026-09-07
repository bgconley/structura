"""Clients for the accepted external ingestion service, without managing its runtime."""

from lib.config import Settings, get_settings
from lib.model_runtime.clients._openai_text import OpenAITextGenerateClient
from lib.model_runtime.clients.qwen_vl import QwenVLClient
from lib.model_runtime.credentials import model_api_key
from lib.model_runtime.http_client import ModelConfigurationError
from lib.model_runtime.profiles import get_model_profile


def ingestion_vision_client(settings: Settings | None = None) -> QwenVLClient:
    resolved = settings or get_settings()
    profile = get_model_profile(resolved.model_ingestion_profile)
    if not profile.supports("document_parse"):
        raise ModelConfigurationError("The ingestion profile does not support document parsing.")
    return QwenVLClient(
        profile=profile,
        http_client_base_url=resolved.model_ingestion_url,
        api_key=model_api_key(
            resolved.model_ingestion_api_key, resolved.model_ingestion_api_key_file
        ),
    )


def ingestion_text_client(settings: Settings | None = None) -> OpenAITextGenerateClient:
    resolved = settings or get_settings()
    profile = get_model_profile(resolved.model_ingestion_profile)
    if not profile.supports("structured_text_extraction"):
        raise ModelConfigurationError("The ingestion profile does not support text extraction.")
    return OpenAITextGenerateClient(
        profile=profile,
        http_client_base_url=resolved.model_ingestion_url,
        api_key=model_api_key(
            resolved.model_ingestion_api_key, resolved.model_ingestion_api_key_file
        ),
    )
