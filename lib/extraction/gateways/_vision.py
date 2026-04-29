from __future__ import annotations

from typing import Protocol

from lib.extraction.granite_prompting import granite_prompt
from lib.extraction.model_output_normalization import normalize_granite_region_output
from lib.extraction.model_output_schemas import model_output_schema_for_task
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
from lib.semantic_annotations.models import SemanticExtractionTask
from lib.storage import ObjectStorage


class VisionClientProtocol(Protocol):
    def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse: ...


class VisionExtractionGateway:
    prompt_version: str
    profile_name: str
    max_image_inputs = 4
    max_output_tokens = 2048
    timeout_seconds = 60

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
        semantic_task: SemanticExtractionTask | None = None,
    ) -> GatewayExtraction:
        model_output_schema = model_output_schema_for_task(
            schema_name=schema_name,
            semantic_task=semantic_task,
        )
        response = self.client.generate(
            VisionGenerateRequest(
                profile_name=self.profile_name,
                prompt_version=self.prompt_version,
                prompt=granite_prompt(
                    source=source,
                    schema_name=schema_name,
                    route_profile=route_profile,
                    semantic_task=semantic_task,
                    model_output_schema=model_output_schema,
                ),
                image_inputs=_image_inputs(
                    source,
                    storage=self.storage,
                    semantic_task=semantic_task,
                    max_images=self.max_image_inputs,
                ),
                response_schema_name=(
                    model_output_schema.name if model_output_schema is not None else schema_name
                ),
                max_output_tokens=self.max_output_tokens,
                temperature=0.0,
                timeout_seconds=self.timeout_seconds,
                response_json_schema=(
                    model_output_schema.schema if model_output_schema is not None else None
                ),
            )
        )
        normalized_json, normalization_json = normalize_granite_region_output(
            document_id=source.document_id,
            schema_name=schema_name,
            model_output_schema_name=(
                model_output_schema.name if model_output_schema is not None else None
            ),
            payload=dict(response.normalized_json),
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
            normalized_json=normalized_json,
            raw_output_json={
                "modelInvoked": True,
                "profileName": response.profile_name,
                "modelName": response.model_name,
                "modelVersion": response.model_version,
                "sourceEngine": response.source_engine,
                "promptVersion": response.prompt_version,
                "inputSha256": list(response.input_sha256),
                "latencyMs": response.latency_ms,
                "finishReason": response.finish_reason,
                "usage": response.usage_json,
                "structuredOutputUsed": response.structured_output_used,
                "structuredOutputFallbackReason": response.structured_output_fallback_reason,
                "confidence": response.confidence_json,
                "rawText": response.raw_text,
                "semanticTask": _semantic_task_json(semantic_task),
                "modelOutputSchema": (
                    model_output_schema.name if model_output_schema is not None else None
                ),
            },
            model_output_schema_name=(
                model_output_schema.name if model_output_schema is not None else None
            ),
            model_output_schema_version=(
                model_output_schema.version if model_output_schema is not None else None
            ),
            normalization_json=normalization_json,
        )


def _image_inputs(
    source: ExtractionSourceDocument,
    *,
    storage: ObjectStorage,
    semantic_task: SemanticExtractionTask | None = None,
    max_images: int = 4,
) -> tuple[ModelImageInput, ...]:
    inputs: list[ModelImageInput] = []
    for page in _candidate_pages(source, semantic_task=semantic_task):
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
        if len(inputs) >= max_images:
            break
    if not inputs:
        raise ModelProtocolError("Vision extraction requires page image assets.")
    return tuple(inputs)


def _candidate_pages(
    source: ExtractionSourceDocument,
    *,
    semantic_task: SemanticExtractionTask | None,
) -> list:
    if semantic_task is None:
        return source.pages
    page_id = _page_id_for_semantic_task(source, semantic_task)
    if page_id is None:
        return source.pages
    return [page for page in source.pages if page.page_id == page_id] or source.pages


def _page_id_for_semantic_task(
    source: ExtractionSourceDocument,
    task: SemanticExtractionTask,
) -> object | None:
    if task.grounding.page_id:
        return task.grounding.page_id
    if task.grounding.element_id:
        page_number = next(
            (
                element.page_number
                for element in source.elements
                if element.element_id == task.grounding.element_id
            ),
            None,
        )
        return _page_id_for_number(source, page_number)
    if task.grounding.table_id:
        page_number = next(
            (
                table.page_number
                for table in source.tables
                if table.table_id == task.grounding.table_id
            ),
            None,
        )
        return _page_id_for_number(source, page_number)
    return None


def _page_id_for_number(
    source: ExtractionSourceDocument,
    page_number: int | None,
) -> object | None:
    if page_number is None:
        return None
    return next((page.page_id for page in source.pages if page.page_number == page_number), None)


def _prompt(
    *,
    source: ExtractionSourceDocument,
    schema_name: str,
    route_profile: str,
    semantic_task: SemanticExtractionTask | None = None,
) -> str:
    base = (
        "Extract evidence-backed structured fields from the provided document page images. "
        f"Target schema: {schema_name}. Route profile: {route_profile}. "
        "Use Docling text only as context; image evidence is authoritative for visual fields. "
        "Return compact candidate JSON; do not transcribe long paragraphs or unrelated fields. "
        "Return JSON only in this shape: "
        '{"normalized":{...target schema JSON...},"confidence":{"overall":0.0,'
        '"schema_fit":0.0}}. Do not include Markdown fences or explanatory text.'
    )
    if semantic_task is None:
        return base
    return (
        f"{base} Semantic task from Qwen annotation: "
        f"type={semantic_task.semantic_type}; granite_task={semantic_task.granite_task}; "
        f"expected_fields={list(semantic_task.expected_fields)}; "
        f"grounding={semantic_task.grounding.kind}; reason={semantic_task.reason or ''}. "
        "For grounded semantic tasks, extract only the visible fields needed for that task; "
        "omit uncertain values instead of adding prose."
    )


def _semantic_task_json(task: SemanticExtractionTask | None) -> dict[str, object] | None:
    if task is None:
        return None
    return {
        "semanticRegionId": str(task.region_id),
        "semanticAnnotationId": str(task.annotation_id),
        "semanticType": task.semantic_type,
        "graniteTask": task.granite_task,
        "targetSchema": task.target_schema,
        "expectedFields": list(task.expected_fields),
        "grounding": {
            "kind": task.grounding.kind,
            "pageId": str(task.grounding.page_id) if task.grounding.page_id else None,
            "elementId": (str(task.grounding.element_id) if task.grounding.element_id else None),
            "tableId": str(task.grounding.table_id) if task.grounding.table_id else None,
        },
        "confidence": task.confidence,
        "reason": task.reason,
    }
