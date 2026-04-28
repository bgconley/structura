from __future__ import annotations

from dataclasses import dataclass

from lib.config import get_settings
from lib.extraction.gateway import DoclingHeuristicGateway
from lib.extraction.gateways.granite_vision import GraniteVisionExtractionGateway
from lib.extraction.gateways.qwen_vl import QwenVLExtractionGateway
from lib.extraction.gateways.routing import (
    ModelRoutingExtractionGateway,
    default_extraction_gateway,
)
from tests.unit.extraction.test_model_gateways import FakeVisionClient, _source_with_page_image


@dataclass
class RecordingDeterministicGateway(DoclingHeuristicGateway):
    called: bool = False

    def extract(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.called = True
        return super().extract(*args, **kwargs)


def test_routing_gateway_uses_qwen_for_handwriting_route() -> None:
    qwen_client = FakeVisionClient(source_engine="qwen3_vl_8b", profile_name="qwen")
    granite_client = FakeVisionClient(source_engine="granite_vision_3b", profile_name="granite")
    deterministic = RecordingDeterministicGateway()
    gateway = ModelRoutingExtractionGateway(
        deterministic=deterministic,
        qwen=QwenVLExtractionGateway(client=qwen_client),
        granite=GraniteVisionExtractionGateway(client=granite_client),
    )

    result = gateway.extract(
        _source_with_page_image(),
        schema_name="invoice",
        route_profile="qwen_primary_review_required",
    )

    assert result.route.source_engine == "qwen3_vl_8b"
    assert qwen_client.request is not None
    assert granite_client.request is None
    assert deterministic.called is False


def test_routing_gateway_uses_granite_for_structured_route() -> None:
    qwen_client = FakeVisionClient(source_engine="qwen3_vl_8b", profile_name="qwen")
    granite_client = FakeVisionClient(source_engine="granite_vision_3b", profile_name="granite")
    gateway = ModelRoutingExtractionGateway(
        deterministic=RecordingDeterministicGateway(),
        qwen=QwenVLExtractionGateway(client=qwen_client),
        granite=GraniteVisionExtractionGateway(client=granite_client),
    )

    result = gateway.extract(
        _source_with_page_image(),
        schema_name="invoice",
        route_profile="docling_plus_structured_extraction",
    )

    assert result.route.source_engine == "granite_vision_3b"
    assert granite_client.request is not None
    assert qwen_client.request is None


def test_default_extraction_gateway_remains_fixture_when_model_mode_is_fixture(monkeypatch) -> None:
    monkeypatch.setenv("STRUCTURA_MODEL_MODE", "fixture")
    get_settings.cache_clear()
    try:
        gateway = default_extraction_gateway()
    finally:
        get_settings.cache_clear()

    assert isinstance(gateway, DoclingHeuristicGateway)
