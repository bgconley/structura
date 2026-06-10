from __future__ import annotations

from dataclasses import replace

from lib.config import get_settings
from lib.extraction.classification import TARGET_EXTRACTION_SCHEMAS
from lib.extraction.gateway import DoclingHeuristicGateway, ExtractionGateway
from lib.extraction.gateways.granite_vision import GraniteVisionExtractionGateway
from lib.extraction.models import ExtractionSourceDocument, GatewayExtraction
from lib.extraction.text_lane.eligibility import (
    LaneDecision,
    text_lane_eligibility,
    text_lane_kvp_eligibility,
)
from lib.extraction.text_lane.gateway import TextLaneAbstention, TextLaneTableExtractionGateway
from lib.extraction.text_lane.kvp_gateway import TextLaneKvpExtractionGateway
from lib.model_runtime.clients.granite_vision import GraniteVisionClient
from lib.model_runtime.http_client import ModelProtocolError
from lib.model_runtime.profiles import get_model_profile
from lib.semantic_annotations.models import SemanticExtractionTask
from lib.semantic_annotations.task_routing import KVP_SEMANTIC_TYPES

DISABLED_ROUTE_PROFILES = {
    "granite_then_qwen_fallback_review_required",
    "qwen_primary_review_required",
}
GRANITE_ROUTE_PROFILES = {
    "docling_plus_structured_extraction",
    "docling_plus_granite_structured",
    "granite_primary_review_required",
}
# Every target extraction schema (including document_observation) routes to
# Granite so non-Granite route profiles cannot silently fall back to the
# deterministic gateway for a structured schema.
STRUCTURED_SCHEMAS = frozenset(TARGET_EXTRACTION_SCHEMAS)


class ModelRoutingExtractionGateway:
    def __init__(
        self,
        *,
        deterministic: ExtractionGateway,
        granite: ExtractionGateway,
        text_lane_tables: TextLaneTableExtractionGateway | None = None,
        text_lane_kvp: TextLaneKvpExtractionGateway | None = None,
    ) -> None:
        self.deterministic = deterministic
        self.granite = granite
        self.text_lane_tables = text_lane_tables
        self.text_lane_kvp = text_lane_kvp

    def extract(
        self,
        source: ExtractionSourceDocument,
        *,
        schema_name: str,
        route_profile: str,
        semantic_task: SemanticExtractionTask | None = None,
    ) -> GatewayExtraction:
        if route_profile in DISABLED_ROUTE_PROFILES:
            raise ModelProtocolError(
                f"Route profile {route_profile} is disabled in Phase 8.5 production. "
                "Qwen is semantic-only; extraction must be Granite or deterministic fixture."
            )
        granite_requested = (
            route_profile in GRANITE_ROUTE_PROFILES or schema_name in STRUCTURED_SCHEMAS
        )
        if granite_requested:
            if semantic_task is None:
                raise ModelProtocolError(
                    "Live Granite extraction requires a grounded semantic region task. "
                    "Broad document-level structured extraction is disabled."
                )
            lane_decision: LaneDecision | None = None
            if self.text_lane_kvp is not None and semantic_task.semantic_type in KVP_SEMANTIC_TYPES:
                lane_decision = text_lane_kvp_eligibility(source, semantic_task=semantic_task)
                if lane_decision.lane == "text":
                    try:
                        return self.text_lane_kvp.extract(
                            source,
                            schema_name=schema_name,
                            route_profile=route_profile,
                            semantic_task=semantic_task,
                            lane_decision=lane_decision,
                        )
                    except TextLaneAbstention as abstention:
                        lane_decision = LaneDecision(
                            lane="vision",
                            reason=f"text_lane_abstained:{abstention.reason}",
                            page_number=lane_decision.page_number,
                        )
            elif self.text_lane_tables is not None:
                lane_decision = text_lane_eligibility(source, semantic_task=semantic_task)
                if lane_decision.lane == "text":
                    try:
                        return self.text_lane_tables.extract(
                            source,
                            schema_name=schema_name,
                            route_profile=route_profile,
                            semantic_task=semantic_task,
                            lane_decision=lane_decision,
                        )
                    except TextLaneAbstention as abstention:
                        lane_decision = LaneDecision(
                            lane="vision",
                            reason=f"text_lane_abstained:{abstention.reason}",
                            page_number=lane_decision.page_number,
                            table_id=lane_decision.table_id,
                        )
            result = self.granite.extract(
                source,
                schema_name=schema_name,
                route_profile=route_profile,
                semantic_task=semantic_task,
            )
            if lane_decision is None:
                return result
            return _with_lane_telemetry(result, lane_decision)
        return self.deterministic.extract(
            source,
            schema_name=schema_name,
            route_profile=route_profile,
            semantic_task=semantic_task,
        )


def _with_lane_telemetry(
    result: GatewayExtraction,
    decision: LaneDecision,
) -> GatewayExtraction:
    return replace(
        result,
        normalization_json={
            **result.normalization_json,
            "lane": decision.lane,
            "laneEligibility": decision.reason,
        },
    )


def default_extraction_gateway() -> ExtractionGateway:
    settings = get_settings()
    deterministic = DoclingHeuristicGateway()
    if settings.model_mode == "fixture":
        return deterministic
    granite_profile = get_model_profile(settings.granite_profile)
    text_lane_tables = (
        TextLaneTableExtractionGateway() if settings.text_lane_tables_enabled else None
    )
    text_lane_kvp = TextLaneKvpExtractionGateway() if settings.text_lane_kvp_enabled else None
    return ModelRoutingExtractionGateway(
        deterministic=deterministic,
        granite=GraniteVisionExtractionGateway(
            client=GraniteVisionClient(
                profile=granite_profile,
                http_client_base_url=settings.model_granite_url,
            )
        ),
        text_lane_tables=text_lane_tables,
        text_lane_kvp=text_lane_kvp,
    )
