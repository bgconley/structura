from __future__ import annotations

import httpx

from lib.model_runtime.clients._openai_vision import OpenAIVisionGenerateClient
from lib.model_runtime.profiles import ModelProfile


class GraniteVisionClient(OpenAIVisionGenerateClient):
    def __init__(
        self,
        *,
        profile: ModelProfile,
        http_client_base_url: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if profile.engine != "granite":
            raise ValueError("GraniteVisionClient requires a Granite profile.")
        super().__init__(
            profile=profile,
            http_client_base_url=http_client_base_url,
            transport=transport,
        )
