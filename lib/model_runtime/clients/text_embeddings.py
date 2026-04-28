from __future__ import annotations

import httpx

from lib.model_runtime.clients._embedding import EmbeddingHttpClient
from lib.model_runtime.profiles import ModelProfile


class TextEmbeddingClient(EmbeddingHttpClient):
    def __init__(
        self,
        *,
        profile: ModelProfile,
        http_client_base_url: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if profile.engine != "text_embedding":
            raise ValueError("TextEmbeddingClient requires a text embedding profile.")
        super().__init__(
            profile=profile,
            http_client_base_url=http_client_base_url,
            requires_image=False,
            transport=transport,
        )
