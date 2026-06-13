from __future__ import annotations

from typing import Any, Protocol, cast

from lib.extraction.expected_field_coverage import normalized_field_name
from lib.extraction.gateways.vision_lane import (
    QWEN_VISION_OBSERVATIONS_SCHEMA,
    QWEN_VISION_PROVIDER,
    VISION_LANE_NAME,
)
from lib.extraction.model_output_schemas import load_model_output_schema
from lib.extraction.models import ExtractionSourceDocument, GatewayExtraction, ModelRoute
from lib.extraction.qwen_vision_prompting import (
    QWEN_VISION_PROMPT_VERSION,
    qwen_vision_observation_prompt,
)
from lib.extraction.region_envelope import (
    EvidenceRef,
    RegionExtractionEnvelope,
    RegionFact,
    ValueType,
    envelope_json,
    to_normalization_projection,
)
from lib.extraction.visual_input_planning import (
    plan_vision_inputs,
    vision_input_mode_from_env,
    visual_input_attempt_json,
    visual_input_mode_env_telemetry,
)
from lib.model_runtime.contracts import VisionGenerateRequest, VisionGenerateResponse
from lib.model_runtime.http_client import ModelProtocolError
from lib.model_runtime.profiles import QWEN_VISION_PROFILE
from lib.semantic_annotations.models import SemanticExtractionTask
from lib.storage import ObjectStorage


class QwenVisionClientProtocol(Protocol):
    def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse: ...


class QwenVisionExtractionGateway:
    prompt_version = QWEN_VISION_PROMPT_VERSION
    profile_name = QWEN_VISION_PROFILE
    max_image_inputs = 1
    max_output_tokens = 1024
    timeout_seconds = 60

    def __init__(
        self,
        *,
        client: QwenVisionClientProtocol,
        storage: ObjectStorage | None = None,
        profile_name: str | None = None,
    ) -> None:
        self.client = client
        self.storage = storage or ObjectStorage()
        self.profile_name = profile_name or self.profile_name

    def extract(
        self,
        source: ExtractionSourceDocument,
        *,
        schema_name: str,
        route_profile: str,
        semantic_task: SemanticExtractionTask | None = None,
    ) -> GatewayExtraction:
        if semantic_task is None:
            raise ModelProtocolError(
                "Qwen vision fallback requires a grounded semantic region task."
            )
        decision = plan_vision_inputs(
            source,
            semantic_task=semantic_task,
            max_images=self.max_image_inputs,
            page_image_loader=self._page_image_bytes,
            mode=vision_input_mode_from_env(),
        )
        model_output_schema = load_model_output_schema(QWEN_VISION_OBSERVATIONS_SCHEMA)
        request = VisionGenerateRequest(
            profile_name=self.profile_name,
            prompt_version=self.prompt_version,
            prompt=qwen_vision_observation_prompt(
                source=source,
                schema_name=schema_name,
                route_profile=route_profile,
                semantic_task=semantic_task,
            ),
            image_inputs=decision.model_inputs,
            response_schema_name=QWEN_VISION_OBSERVATIONS_SCHEMA,
            response_json_schema=model_output_schema.schema,
            max_output_tokens=self.max_output_tokens,
            temperature=0.0,
            timeout_seconds=self.timeout_seconds,
        )
        response = self.client.generate(request)
        model_output_payload = dict(response.normalized_json)
        observations, rejected = _region_observations(
            payload=model_output_payload,
            source=source,
            semantic_task=semantic_task,
            source_engine=response.source_engine,
            visual_plan=decision.primary_plan.as_json() if decision.primary_plan else None,
        )
        envelope = RegionExtractionEnvelope(
            document_id=str(source.document_id),
            semantic_annotation_id=str(semantic_task.annotation_id),
            semantic_region_id=str(semantic_task.region_id),
            resolved_document_type="document_observation",
            semantic_type=semantic_task.semantic_type,
            target_schema="document_observation",
            model_output_schema_name=QWEN_VISION_OBSERVATIONS_SCHEMA,
            coverage={
                "schema_name": "document_observation",
                "schema_version": "v1",
                "confidence": dict(response.confidence_json),
                "metadata": {
                    "visualDerived": True,
                    "visionProvider": QWEN_VISION_PROVIDER,
                    "requiresReview": True,
                },
            },
            observations=observations,
            warnings=["qwen_vision_values_require_review"],
        )
        visual_input_plan = decision.primary_plan.as_json() if decision.primary_plan else None
        attempts = [
            visual_input_attempt_json(
                decision=decision,
                useful=bool(observations),
                failure_reason=None if observations else "no_review_observations",
            )
        ]
        normalization_json = {
            "mapper": QWEN_VISION_OBSERVATIONS_SCHEMA,
            "lane": VISION_LANE_NAME,
            "visionProvider": QWEN_VISION_PROVIDER,
            "regionEnvelope": envelope_json(envelope),
            "regionEnvelopeVersion": "phase8_5-region-envelope-v1",
            "normalizedProjectionDerivedFromEnvelope": True,
            "visualInputPlan": visual_input_plan,
            "visualInputAttempts": attempts,
        }
        return GatewayExtraction(
            schema_name="document_observation",
            schema_version="v1",
            route=ModelRoute(
                source_engine=response.source_engine,
                model_name=response.model_name,
                model_version=response.model_version,
                prompt_version=response.prompt_version,
                route_profile=route_profile,
            ),
            normalized_json=to_normalization_projection(envelope),
            raw_output_json={
                "modelInvoked": True,
                "lane": VISION_LANE_NAME,
                "visionProvider": QWEN_VISION_PROVIDER,
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
                "confidence": response.confidence_json,
                "rawText": response.raw_text,
                "visualInputPlan": visual_input_plan,
                "visualInputAttempts": attempts,
                "visualInputModeEnv": visual_input_mode_env_telemetry(),
                "modelOutputSchema": QWEN_VISION_OBSERVATIONS_SCHEMA,
                "modelOutputPayload": model_output_payload,
                "rejectedObservations": rejected,
            },
            model_output_schema_name=QWEN_VISION_OBSERVATIONS_SCHEMA,
            model_output_schema_version=model_output_schema.version,
            normalization_json=normalization_json,
            metadata={
                "lane": VISION_LANE_NAME,
                "visionProvider": QWEN_VISION_PROVIDER,
                "visualInputPlan": visual_input_plan,
                "visualInputAttempts": attempts,
            },
        )

    def _page_image_bytes(self, page: object) -> bytes | None:
        image_bytes = getattr(page, "image_bytes", None)
        image_asset_uri = getattr(page, "image_asset_uri", None)
        if image_bytes is None and image_asset_uri:
            image_bytes = self.storage.path_for_uri(image_asset_uri).read_bytes()
        return image_bytes


def _region_observations(
    *,
    payload: dict[str, Any],
    source: ExtractionSourceDocument,
    semantic_task: SemanticExtractionTask,
    source_engine: str,
    visual_plan: dict[str, object] | None,
) -> tuple[list[RegionFact], list[dict[str, object]]]:
    raw_items = payload.get("observations")
    if not isinstance(raw_items, list):
        return [], []
    docling_text = _docling_text_for_region(source, semantic_task)
    text_present = bool(docling_text)
    expected_fields = _expected_field_names(semantic_task)
    observations: list[RegionFact] = []
    rejected: list[dict[str, object]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        field_name = _non_empty_str(item.get("field_name"))
        if field_name is None:
            continue
        if text_present and not expected_fields:
            rejected.append(
                {
                    "fieldName": field_name,
                    "reason": "no_expected_fields_for_text_present_region",
                }
            )
            continue
        if text_present and normalized_field_name(field_name) not in expected_fields:
            rejected.append(
                {
                    "fieldName": field_name,
                    "reason": "unexpected_field_for_text_present_region",
                }
            )
            continue
        quote = _optional_str(item.get("quote"))
        if text_present and not quote:
            rejected.append(
                {"fieldName": field_name, "reason": "missing_quote_for_text_present_region"}
            )
            continue
        if quote and text_present and not _quote_in_text(quote, docling_text):
            rejected.append({"fieldName": field_name, "reason": "quote_not_found_in_docling_text"})
            continue
        if text_present:
            rejected.append(
                {
                    "fieldName": field_name,
                    "reason": "text_present_qwen_value_not_admitted",
                }
            )
            continue
        value = item.get("value")
        if value in (None, ""):
            continue
        observations.append(
            RegionFact(
                name=field_name,
                value=value,
                value_type=_value_type(item.get("value_type")),
                confidence=_confidence(item.get("confidence")),
                source_text=quote,
                evidence=[
                    _evidence_ref(
                        source=source,
                        semantic_task=semantic_task,
                        source_engine=source_engine,
                        source_text=quote,
                        visual_plan=visual_plan,
                    )
                ],
                source_payload={
                    "family": "qwen_vision",
                    "field_name": field_name,
                    "value": value,
                    "value_type": _value_type(item.get("value_type")),
                    "source_text": quote,
                    "confidence": _confidence(item.get("confidence")),
                    "visualDerived": True,
                    "requiresReview": True,
                    "visionProvider": QWEN_VISION_PROVIDER,
                    "semantic_type": semantic_task.semantic_type,
                },
            )
        )
    return observations, rejected


def _expected_field_names(semantic_task: SemanticExtractionTask) -> set[str]:
    return {
        normalized
        for raw in semantic_task.expected_fields
        if (normalized := normalized_field_name(str(raw)))
    }


def _evidence_ref(
    *,
    source: ExtractionSourceDocument,
    semantic_task: SemanticExtractionTask,
    source_engine: str,
    source_text: str | None,
    visual_plan: dict[str, object] | None,
) -> EvidenceRef:
    page = _grounded_page(source, semantic_task)
    return EvidenceRef(
        document_id=str(source.document_id),
        semantic_annotation_id=str(semantic_task.annotation_id),
        semantic_region_id=str(semantic_task.region_id),
        page_number=page.page_number if page is not None else None,
        page_id=str(page.page_id) if page is not None else None,
        source_engine=source_engine,
        source_text=source_text,
        visual_input_scope=_optional_str((visual_plan or {}).get("scope")),
        visual_input_sha256=_optional_str((visual_plan or {}).get("inputSha256")),
        source_page_image_sha256=_optional_str((visual_plan or {}).get("sourcePageImageSha256")),
    )


def _grounded_page(
    source: ExtractionSourceDocument,
    semantic_task: SemanticExtractionTask,
):
    page_id = semantic_task.grounding.page_id
    if page_id is not None:
        for page in source.pages:
            if page.page_id == page_id:
                return page
    return source.pages[0] if source.pages else None


def _docling_text_for_region(
    source: ExtractionSourceDocument,
    semantic_task: SemanticExtractionTask,
) -> str:
    page = _grounded_page(source, semantic_task)
    if page is None or page.has_text_layer is False:
        return ""
    return " ".join(page.text.split())


def _quote_in_text(quote: str, text: str) -> bool:
    return _normalized_text(quote) in _normalized_text(text)


def _normalized_text(value: str) -> str:
    return " ".join(value.lower().split())


def _non_empty_str(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_str(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _value_type(value: object) -> ValueType:
    normalized = str(value or "string").strip().lower()
    if normalized in {
        "string",
        "number",
        "money",
        "date",
        "boolean",
        "object",
        "array",
        "null",
    }:
        return cast(ValueType, normalized)
    return "string"


def _confidence(value: object) -> float | None:
    try:
        confidence = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if 0.0 <= confidence <= 1.0:
        return confidence
    return None
