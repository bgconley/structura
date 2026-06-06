from __future__ import annotations

from lib.config import get_settings
from lib.extraction.gateway import DoclingHeuristicGateway, ExtractionGateway
from lib.extraction.gateways.granite_vision import GraniteVisionExtractionGateway
from lib.extraction.models import ExtractionSourceDocument, GatewayExtraction
from lib.model_runtime.clients.granite_vision import GraniteVisionClient
from lib.model_runtime.http_client import ModelProtocolError
from lib.model_runtime.profiles import get_model_profile
from lib.semantic_annotations.models import SemanticExtractionTask

DISABLED_ROUTE_PROFILES = {
    "granite_then_qwen_fallback_review_required",
    "qwen_primary_review_required",
}
GRANITE_ROUTE_PROFILES = {
    "docling_plus_structured_extraction",
    "docling_plus_granite_structured",
    "granite_primary_review_required",
}
STRUCTURED_SCHEMAS = {"receipt", "invoice", "medical_eob"}


class ModelRoutingExtractionGateway:
    def __init__(
        self,
        *,
        deterministic: ExtractionGateway,
        granite: ExtractionGateway,
    ) -> None:
        self.deterministic = deterministic
        self.granite = granite

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
            return self.granite.extract(
                source,
                schema_name=schema_name,
                route_profile=route_profile,
                semantic_task=semantic_task,
            )
        return self.deterministic.extract(
            source,
            schema_name=schema_name,
            route_profile=route_profile,
            semantic_task=semantic_task,
        )


def default_extraction_gateway() -> ExtractionGateway:
    settings = get_settings()
    deterministic = DoclingHeuristicGateway()
    if settings.model_mode == "fixture":
        return deterministic
    granite_profile = get_model_profile(settings.granite_profile)
    return ModelRoutingExtractionGateway(
        deterministic=deterministic,
        granite=GraniteVisionExtractionGateway(
            client=GraniteVisionClient(
                profile=granite_profile,
                http_client_base_url=settings.model_granite_url,
            )
        ),
    )
