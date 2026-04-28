from __future__ import annotations

from lib.config import get_settings
from lib.extraction.gateway import DoclingHeuristicGateway, ExtractionGateway
from lib.extraction.gateways.granite_vision import GraniteVisionExtractionGateway
from lib.extraction.gateways.qwen_vl import QwenVLExtractionGateway
from lib.extraction.models import ExtractionSourceDocument, GatewayExtraction
from lib.model_runtime.clients.granite_vision import GraniteVisionClient
from lib.model_runtime.clients.qwen_vl import QwenVLClient
from lib.model_runtime.http_client import ModelRuntimeError
from lib.model_runtime.profiles import get_model_profile

QWEN_ROUTE_PROFILES = {"qwen_primary_review_required"}
GRANITE_ROUTE_PROFILES = {
    "docling_plus_structured_extraction",
    "docling_plus_granite_structured",
    "granite_primary_review_required",
    "granite_then_qwen_fallback_review_required",
}
STRUCTURED_SCHEMAS = {"receipt", "invoice", "medical_eob"}


class ModelRoutingExtractionGateway:
    def __init__(
        self,
        *,
        deterministic: ExtractionGateway,
        qwen: ExtractionGateway,
        granite: ExtractionGateway,
    ) -> None:
        self.deterministic = deterministic
        self.qwen = qwen
        self.granite = granite

    def extract(
        self,
        source: ExtractionSourceDocument,
        *,
        schema_name: str,
        route_profile: str,
    ) -> GatewayExtraction:
        if route_profile in QWEN_ROUTE_PROFILES:
            return self.qwen.extract(source, schema_name=schema_name, route_profile=route_profile)
        if route_profile == "granite_then_qwen_fallback_review_required":
            return self._granite_then_qwen(
                source,
                schema_name=schema_name,
                route_profile=route_profile,
            )
        if route_profile in GRANITE_ROUTE_PROFILES or schema_name in STRUCTURED_SCHEMAS:
            return self.granite.extract(
                source,
                schema_name=schema_name,
                route_profile=route_profile,
            )
        return self.deterministic.extract(
            source,
            schema_name=schema_name,
            route_profile=route_profile,
        )

    def _granite_then_qwen(
        self,
        source: ExtractionSourceDocument,
        *,
        schema_name: str,
        route_profile: str,
    ) -> GatewayExtraction:
        try:
            return self.granite.extract(
                source,
                schema_name=schema_name,
                route_profile=route_profile,
            )
        except ModelRuntimeError:
            return self.qwen.extract(
                source,
                schema_name=schema_name,
                route_profile=route_profile,
            )


def default_extraction_gateway() -> ExtractionGateway:
    settings = get_settings()
    deterministic = DoclingHeuristicGateway()
    if settings.model_mode == "fixture":
        return deterministic
    qwen_profile = get_model_profile(settings.qwen_profile)
    granite_profile = get_model_profile(settings.granite_profile)
    return ModelRoutingExtractionGateway(
        deterministic=deterministic,
        qwen=QwenVLExtractionGateway(
            client=QwenVLClient(
                profile=qwen_profile,
                http_client_base_url=settings.model_qwen_url,
            )
        ),
        granite=GraniteVisionExtractionGateway(
            client=GraniteVisionClient(
                profile=granite_profile,
                http_client_base_url=settings.model_granite_url,
            )
        ),
    )
