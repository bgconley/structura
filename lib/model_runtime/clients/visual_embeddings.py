from __future__ import annotations

import httpx

from lib.model_runtime.clients._embedding import EmbeddingHttpClient
from lib.model_runtime.profiles import ModelProfile


class VisualEmbeddingClient(EmbeddingHttpClient):
    def __init__(
        self,
        *,
        profile: ModelProfile,
        http_client_base_url: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if profile.engine != "visual_embedding":
            raise ValueError("VisualEmbeddingClient requires a visual embedding profile.")
        super().__init__(
            profile=profile,
            http_client_base_url=http_client_base_url,
            requires_image=True,
            transport=transport,
        )


class VisualQueryEmbeddingClient(EmbeddingHttpClient):
    def __init__(
        self,
        *,
        profile: ModelProfile,
        http_client_base_url: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if profile.engine != "visual_embedding":
            raise ValueError("VisualQueryEmbeddingClient requires a visual embedding profile.")
        super().__init__(
            profile=profile,
            http_client_base_url=http_client_base_url,
            requires_image=False,
            transport=transport,
        )
