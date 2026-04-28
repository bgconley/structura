from __future__ import annotations

import httpx

from lib.model_runtime.clients._openai_vision import OpenAIVisionGenerateClient
from lib.model_runtime.profiles import ModelProfile


class QwenVLClient(OpenAIVisionGenerateClient):
    def __init__(
        self,
        *,
        profile: ModelProfile,
        http_client_base_url: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if profile.engine != "qwen":
            raise ValueError("QwenVLClient requires a Qwen profile.")
        super().__init__(
            profile=profile,
            http_client_base_url=http_client_base_url,
            transport=transport,
        )
