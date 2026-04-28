from __future__ import annotations

from typing import Protocol

from lib.extraction.models import (
    ExtractionSourceDocument,
    GatewayExtraction,
    ModelRoute,
)
from lib.model_runtime.contracts import (
    ModelImageInput,
    VisionGenerateRequest,
    VisionGenerateResponse,
)
from lib.model_runtime.http_client import ModelProtocolError
from lib.storage import ObjectStorage


class VisionClientProtocol(Protocol):
    def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse: ...


class VisionExtractionGateway:
    prompt_version: str
    profile_name: str

    def __init__(
        self,
        *,
        client: VisionClientProtocol,
        storage: ObjectStorage | None = None,
    ) -> None:
        self.client = client
        self.storage = storage or ObjectStorage()

    def extract(
        self,
        source: ExtractionSourceDocument,
        *,
        schema_name: str,
        route_profile: str,
    ) -> GatewayExtraction:
        response = self.client.generate(
            VisionGenerateRequest(
                profile_name=self.profile_name,
                prompt_version=self.prompt_version,
                prompt=_prompt(source=source, schema_name=schema_name, route_profile=route_profile),
                image_inputs=_image_inputs(source, storage=self.storage),
                response_schema_name=schema_name,
                max_output_tokens=2048,
                temperature=0.0,
                timeout_seconds=60,
            )
        )
        return GatewayExtraction(
            schema_name=schema_name,
            schema_version="v1",
            route=ModelRoute(
                source_engine=response.source_engine,
                model_name=response.model_name,
                model_version=response.model_version,
                prompt_version=response.prompt_version,
                route_profile=route_profile,
            ),
            normalized_json=dict(response.normalized_json),
            raw_output_json={
                "modelInvoked": True,
                "profileName": response.profile_name,
                "modelName": response.model_name,
                "modelVersion": response.model_version,
                "sourceEngine": response.source_engine,
                "promptVersion": response.prompt_version,
                "inputSha256": list(response.input_sha256),
                "latencyMs": response.latency_ms,
                "confidence": response.confidence_json,
                "rawText": response.raw_text,
            },
        )


def _image_inputs(
    source: ExtractionSourceDocument,
    *,
    storage: ObjectStorage,
) -> tuple[ModelImageInput, ...]:
    inputs: list[ModelImageInput] = []
    for page in source.pages:
        image_bytes = page.image_bytes
        if image_bytes is None and page.image_asset_uri:
            image_bytes = storage.path_for_uri(page.image_asset_uri).read_bytes()
        if not image_bytes or not page.image_mime_type:
            continue
        inputs.append(
            ModelImageInput(
                content=image_bytes,
                mime_type=page.image_mime_type,
                sha256=page.image_sha256 or "",
            )
        )
    if not inputs:
        raise ModelProtocolError("Vision extraction requires page image assets.")
    return tuple(inputs)


def _prompt(
    *,
    source: ExtractionSourceDocument,
    schema_name: str,
    route_profile: str,
) -> str:
    return (
        "Extract evidence-backed structured fields from the provided document page images. "
        f"Target schema: {schema_name}. Route profile: {route_profile}. "
        "Use Docling text only as context; image evidence is authoritative for visual fields."
    )
