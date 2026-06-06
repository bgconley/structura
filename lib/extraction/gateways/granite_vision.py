from __future__ import annotations

from lib.extraction.gateways._vision import VisionClientProtocol, VisionExtractionGateway
from lib.extraction.granite_budgets import (
    GraniteTaskBudget,
    granite_budget_for_task,
    granite_length_retry_budget,
)
from lib.extraction.models import ExtractionSourceDocument, GatewayExtraction
from lib.model_runtime.http_client import ModelProtocolError
from lib.model_runtime.profiles import GRANITE_VISION_PROFILE
from lib.semantic_annotations.models import SemanticExtractionTask


class GraniteVisionExtractionGateway(VisionExtractionGateway):
    prompt_version = "phase8_5-granite-structured-v1"
    profile_name = GRANITE_VISION_PROFILE
    max_image_inputs = 1

    def __init__(self, *, client: VisionClientProtocol) -> None:
        super().__init__(client=client)

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
                "Granite extraction requires a grounded semantic region task. "
                "Broad document-level Granite extraction is disabled."
            )
        return super().extract(
            source,
            schema_name=schema_name,
            route_profile=route_profile,
            semantic_task=semantic_task,
        )

    def _request_budget(
        self,
        *,
        schema_name: str,
        semantic_task: SemanticExtractionTask | None,
    ) -> GraniteTaskBudget:
        return granite_budget_for_task(
            schema_name=schema_name,
            semantic_task=semantic_task,
        )

    def _retry_budget_after_protocol_error(
        self,
        exc: ModelProtocolError,
        budget: GraniteTaskBudget,
    ) -> GraniteTaskBudget | None:
        if not _is_length_truncation_error(exc):
            return None
        return granite_length_retry_budget(budget)


def _is_length_truncation_error(exc: ModelProtocolError) -> bool:
    if exc.details.get("finish_reason") == "length":
        return True
    message = str(exc).lower()
    return "truncated" in message and "json" in message
