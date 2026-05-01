from __future__ import annotations

from lib.extraction.gateways._vision import VisionClientProtocol, VisionExtractionGateway
from lib.extraction.granite_budgets import GraniteTaskBudget, granite_budget_for_task
from lib.model_runtime.profiles import GRANITE_VISION_PROFILE
from lib.semantic_annotations.models import SemanticExtractionTask


class GraniteVisionExtractionGateway(VisionExtractionGateway):
    prompt_version = "phase8_5-granite-structured-v1"
    profile_name = GRANITE_VISION_PROFILE
    max_image_inputs = 1

    def __init__(self, *, client: VisionClientProtocol) -> None:
        super().__init__(client=client)

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
