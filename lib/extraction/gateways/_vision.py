from __future__ import annotations

from typing import Protocol

from lib.extraction.contract_registry import resolved_document_type_from_task_metadata
from lib.extraction.docling_table_quality import DoclingTableQuality, evaluate_docling_table_quality
from lib.extraction.evidence_context import evidence_context_for_task
from lib.extraction.granite_budgets import GraniteTaskBudget
from lib.extraction.granite_prompting import granite_prompt
from lib.extraction.model_output_normalization import normalize_granite_region_output
from lib.extraction.model_output_schemas import ModelOutputSchema, model_output_schema_for_task
from lib.extraction.models import (
    ExtractionSourceDocument,
    GatewayExtraction,
    ModelRoute,
)
from lib.extraction.visual_input_planning import (
    crop_retry_allowed,
    is_useful_granite_output,
    plan_granite_visual_inputs,
    visual_input_attempt_json,
    visual_input_mode_from_env,
)
from lib.extraction.visual_input_types import VisualInputDecision
from lib.model_runtime.contracts import (
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
        if semantic_task is not None and model_output_schema is None:
            raise ModelProtocolError(
                "Selected Granite semantic-region task is missing a model-output contract."
            )
        budget = self._request_budget(
            schema_name=schema_name,
            semantic_task=semantic_task,
        )
        visual_mode = visual_input_mode_from_env()
        decision = plan_granite_visual_inputs(
            source,
            semantic_task=semantic_task,
            max_images=self.max_image_inputs,
            page_image_loader=self._page_image_bytes,
            mode=visual_mode,
        )
        response, response_budget, model_request_attempts = self._generate_with_budget(
            source=source,
            schema_name=schema_name,
            route_profile=route_profile,
            semantic_task=semantic_task,
            model_output_schema=model_output_schema,
            decision=decision,
            budget=budget,
        )
        model_output_payload = dict(response.normalized_json)
        normalized_json, normalization_json = normalize_granite_region_output(
            document_id=source.document_id,
            schema_name=schema_name,
            model_output_schema_name=(
                model_output_schema.name if model_output_schema is not None else None
            ),
            payload=model_output_payload,
            evidence_context=evidence_context_for_task(
                source=source,
                semantic_task=semantic_task,
                source_engine=response.source_engine,
                visual_plan=decision.primary_plan,
            ),
            semantic_type=semantic_task.semantic_type if semantic_task is not None else None,
            target_schema=schema_name,
            resolved_document_type=_resolved_document_type(semantic_task, schema_name),
            docling_table_quality=_docling_table_quality(source, semantic_task),
        )
        useful = is_useful_granite_output(
            normalized_json=normalized_json,
            normalization_json=normalization_json,
            semantic_task=semantic_task,
        )
        attempts = [
            visual_input_attempt_json(
                decision=decision,
                useful=useful,
                failure_reason=None if useful else "output_not_useful",
            )
        ]
        if not useful and budget.max_attempts > 1 and crop_retry_allowed(decision):
            retry_decision = plan_granite_visual_inputs(
                source,
                semantic_task=semantic_task,
                max_images=self.max_image_inputs,
                page_image_loader=self._page_image_bytes,
                mode=visual_mode,
                retry_scope="full_page_retry",
            )
            (
                retry_response,
                retry_response_budget,
                retry_model_request_attempts,
            ) = self._generate_with_budget(
                source=source,
                schema_name=schema_name,
                route_profile=route_profile,
                semantic_task=semantic_task,
                model_output_schema=model_output_schema,
                decision=retry_decision,
                budget=budget,
            )
            retry_model_output_payload = dict(retry_response.normalized_json)
            retry_normalized_json, retry_normalization_json = normalize_granite_region_output(
                document_id=source.document_id,
                schema_name=schema_name,
                model_output_schema_name=(
                    model_output_schema.name if model_output_schema is not None else None
                ),
                payload=retry_model_output_payload,
                evidence_context=evidence_context_for_task(
                    source=source,
                    semantic_task=semantic_task,
                    source_engine=retry_response.source_engine,
                    visual_plan=retry_decision.primary_plan,
                ),
                semantic_type=semantic_task.semantic_type if semantic_task is not None else None,
                target_schema=schema_name,
                resolved_document_type=_resolved_document_type(semantic_task, schema_name),
                docling_table_quality=_docling_table_quality(source, semantic_task),
            )
            retry_useful = is_useful_granite_output(
                normalized_json=retry_normalized_json,
                normalization_json=retry_normalization_json,
                semantic_task=semantic_task,
            )
            attempts.append(
                visual_input_attempt_json(
                    decision=retry_decision,
                    useful=retry_useful,
                    failure_reason=None if retry_useful else "full_page_retry_output_not_useful",
                )
            )
            response = retry_response
            response_budget = retry_response_budget
            model_request_attempts = retry_model_request_attempts
            model_output_payload = retry_model_output_payload
            normalized_json = retry_normalized_json
            normalization_json = {
                **retry_normalization_json,
                "fallbackFromVisualInputScope": (
                    decision.primary_plan.effective_scope if decision.primary_plan else None
                ),
            }
            decision = retry_decision
        visual_input_plan = decision.primary_plan.as_json() if decision.primary_plan else None
        raw_output_json = {
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
            "confidence": response.confidence_json,
            "rawText": response.raw_text,
            "semanticTask": _semantic_task_json(semantic_task),
            "visualInputPlan": visual_input_plan,
            "visualInputAttempts": attempts,
            "requestBudget": {
                "maxOutputTokens": response_budget.max_output_tokens,
                "timeoutSeconds": response_budget.timeout_seconds,
                "maxAttempts": response_budget.max_attempts,
            },
            "modelOutputSchema": (
                model_output_schema.name if model_output_schema is not None else None
            ),
            "modelOutputPayload": model_output_payload,
        }
        if model_request_attempts is not None:
            raw_output_json["modelRequestAttempts"] = model_request_attempts
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
            raw_output_json=raw_output_json,
            model_output_schema_name=(
                model_output_schema.name if model_output_schema is not None else None
            ),
            model_output_schema_version=(
                model_output_schema.version if model_output_schema is not None else None
            ),
            normalization_json=normalization_json,
            metadata={
                "visualInputPlan": visual_input_plan,
                "visualInputAttempts": attempts,
            },
        )

    def _generate_with_budget(
        self,
        *,
        source: ExtractionSourceDocument,
        schema_name: str,
        route_profile: str,
        semantic_task: SemanticExtractionTask | None,
        model_output_schema: ModelOutputSchema | None,
        decision: VisualInputDecision,
        budget: GraniteTaskBudget,
    ) -> tuple[VisionGenerateResponse, GraniteTaskBudget, list[dict[str, object]] | None]:
        request = self._request(
            source=source,
            schema_name=schema_name,
            route_profile=route_profile,
            semantic_task=semantic_task,
            model_output_schema=model_output_schema,
            decision=decision,
            budget=budget,
        )
        try:
            return self.client.generate(request), budget, None
        except ModelProtocolError as exc:
            retry_budget = self._retry_budget_after_protocol_error(exc, budget)
            first_reason = "length_truncated"
            retry_reason = "length_truncated_retry"
            if retry_budget is None:
                if not _is_structured_output_generation_error(exc) or budget.max_attempts <= 1:
                    raise
                retry_budget = budget
                first_reason = "structured_output_invalid"
                retry_reason = "structured_output_retry"
            attempts = [
                _model_request_attempt_json(
                    attempt=1,
                    status="failed",
                    reason=first_reason,
                    budget=budget,
                )
            ]
            retry_request = self._request(
                source=source,
                schema_name=schema_name,
                route_profile=route_profile,
                semantic_task=semantic_task,
                model_output_schema=model_output_schema,
                decision=decision,
                budget=retry_budget,
            )
            try:
                response = self.client.generate(retry_request)
            except ModelProtocolError as retry_exc:
                retry_exc.details.setdefault(
                    "model_request_attempts",
                    attempts
                    + [
                        _model_request_attempt_json(
                            attempt=2,
                            status="failed",
                            reason=retry_reason,
                            budget=retry_budget,
                        )
                    ],
                )
                raise
            attempts.append(
                _model_request_attempt_json(
                    attempt=2,
                    status="succeeded",
                    reason=retry_reason,
                    budget=retry_budget,
                )
            )
            return response, retry_budget, attempts

    def _request(
        self,
        *,
        source: ExtractionSourceDocument,
        schema_name: str,
        route_profile: str,
        semantic_task: SemanticExtractionTask | None,
        model_output_schema: ModelOutputSchema | None,
        decision: VisualInputDecision,
        budget: GraniteTaskBudget,
    ) -> VisionGenerateRequest:
        return VisionGenerateRequest(
            profile_name=self.profile_name,
            prompt_version=self.prompt_version,
            prompt=granite_prompt(
                source=source,
                schema_name=schema_name,
                route_profile=route_profile,
                semantic_task=semantic_task,
                model_output_schema=model_output_schema,
            ),
            image_inputs=decision.model_inputs,
            response_schema_name=(
                model_output_schema.name if model_output_schema is not None else schema_name
            ),
            max_output_tokens=budget.max_output_tokens,
            temperature=0.0,
            timeout_seconds=budget.timeout_seconds,
            response_json_schema=(
                model_output_schema.schema if model_output_schema is not None else None
            ),
        )

    def _page_image_bytes(self, page: object) -> bytes | None:
        image_bytes = getattr(page, "image_bytes", None)
        image_asset_uri = getattr(page, "image_asset_uri", None)
        if image_bytes is None and image_asset_uri:
            image_bytes = self.storage.path_for_uri(image_asset_uri).read_bytes()
        return image_bytes

    def _request_budget(
        self,
        *,
        schema_name: str,
        semantic_task: SemanticExtractionTask | None,
    ) -> GraniteTaskBudget:
        return GraniteTaskBudget(
            max_output_tokens=self.max_output_tokens,
            timeout_seconds=self.timeout_seconds,
            max_attempts=1,
        )

    def _retry_budget_after_protocol_error(
        self,
        _exc: ModelProtocolError,
        _budget: GraniteTaskBudget,
    ) -> GraniteTaskBudget | None:
        return None


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


def _model_request_attempt_json(
    *,
    attempt: int,
    status: str,
    reason: str,
    budget: GraniteTaskBudget,
) -> dict[str, object]:
    return {
        "attempt": attempt,
        "status": status,
        "reason": reason,
        "maxOutputTokens": budget.max_output_tokens,
    }


def _is_structured_output_generation_error(exc: ModelProtocolError) -> bool:
    message = str(exc).lower()
    if message in {
        "vision model content is not valid json.",
        "vision model json content must be an object.",
        "vision model json content does not match response schema.",
        "vision model response message content is empty.",
    }:
        return True
    return "validator" in exc.details and "path" in exc.details


def _resolved_document_type(
    task: SemanticExtractionTask | None,
    schema_name: str,
) -> str:
    if task is None:
        return schema_name
    return resolved_document_type_from_task_metadata(
        metadata=task.metadata,
        semantic_type=task.semantic_type,
        target_schema=schema_name,
    )


def _docling_table_quality(
    source: ExtractionSourceDocument,
    task: SemanticExtractionTask | None,
) -> DoclingTableQuality | None:
    if task is None or task.grounding.table_id is None:
        return None
    table = next(
        (candidate for candidate in source.tables if candidate.table_id == task.grounding.table_id),
        None,
    )
    if table is None:
        return None
    return evaluate_docling_table_quality(
        table,
        continuation_risk=bool(task.metadata.get("continuation_group")),
    )
