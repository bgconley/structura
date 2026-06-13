from __future__ import annotations

import inspect
from dataclasses import dataclass, replace
from uuid import uuid4

import pytest

from lib.config import get_settings
from lib.extraction.gateway import DoclingHeuristicGateway
from lib.extraction.gateways.granite_vision import GraniteVisionExtractionGateway
from lib.extraction.gateways.routing import (
    ModelRoutingExtractionGateway,
    default_extraction_gateway,
)
from lib.extraction.gateways.vision_lane import (
    GRANITE_VISION_PROVIDER,
    QWEN_VISION_PROVIDER,
    VISION_LANE_NAME,
)
from lib.extraction.models import ExtractionSourceDocument, GatewayExtraction, ModelRoute
from lib.extraction.text_lane.kvp_gateway import TextLaneKvpExtractionGateway
from lib.extraction.text_lane.span_selection import SpanSelection
from lib.model_runtime.http_client import ModelProtocolError
from lib.semantic_annotations.models import SemanticExtractionTask, SemanticGroundingRef
from tests.unit.extraction.test_model_gateways import FakeVisionClient, _source_with_page_image


@dataclass
class RecordingDeterministicGateway(DoclingHeuristicGateway):
    called: bool = False

    def extract(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.called = True
        return super().extract(*args, **kwargs)


def _invoice_semantic_task(source: ExtractionSourceDocument) -> SemanticExtractionTask:
    return SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="invoice_line_item_table",
        granite_task="tables_json",
        target_schema="invoice",
        expected_fields=("line_items", "total_amount"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
        reason="Qwen identified a grounded invoice table.",
        confidence=0.92,
    )


def _kvp_semantic_task(source: ExtractionSourceDocument) -> SemanticExtractionTask:
    return SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=source.document_id,
        semantic_type="payment_summary",
        granite_task="kvp",
        target_schema="document_observation",
        expected_fields=("invoice_total",),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
        reason="Qwen identified a payment summary.",
        confidence=0.88,
    )


def _source_with_readable_kvp_text() -> ExtractionSourceDocument:
    source = _source_with_page_image()
    text = " ".join(["Invoice total $42 due on receipt."] * 20)
    return replace(
        source,
        pages=[replace(source.pages[0], text=text, has_text_layer=True)],
        elements=[replace(source.elements[0], text="Invoice total $42")],
    )


class NoMatchSpanSelector:
    def select_spans(self, *, family, expected_keys, spans):  # noqa: ANN001
        del family, spans
        return SpanSelection(
            selections={key: None for key in expected_keys},
            model_name="fake-selector",
            model_version="test",
            prompt_version="text_lane_span_selection.v1",
        )


class RecordingVisionGateway:
    def __init__(self, *, source_engine: str, provider: str) -> None:
        self.source_engine = source_engine
        self.provider = provider
        self.calls = 0
        self.semantic_task: SemanticExtractionTask | None = None

    def extract(
        self,
        source: ExtractionSourceDocument,
        *,
        schema_name: str,
        route_profile: str,
        semantic_task: SemanticExtractionTask | None = None,
    ) -> GatewayExtraction:
        self.calls += 1
        self.semantic_task = semantic_task
        return GatewayExtraction(
            schema_name=schema_name,
            schema_version="v1",
            route=ModelRoute(
                source_engine=self.source_engine,
                model_name=self.provider,
                model_version="test",
                prompt_version=f"phase8_5-{self.provider}-vision-test",
                route_profile=route_profile,
            ),
            normalized_json={"schema_name": schema_name, "document_id": str(source.document_id)},
            raw_output_json={"modelInvoked": True},
            normalization_json={
                "lane": VISION_LANE_NAME,
                "visionProvider": self.provider,
            },
        )


def test_live_routing_gateway_has_no_qwen_extraction_dependency() -> None:
    constructor = inspect.signature(ModelRoutingExtractionGateway)
    routing_source = inspect.getsource(ModelRoutingExtractionGateway)

    assert "qwen" not in constructor.parameters
    assert "QwenVLExtractionGateway" not in routing_source


def test_routing_gateway_accepts_neutral_vision_gateway_name() -> None:
    constructor = inspect.signature(ModelRoutingExtractionGateway)
    assert "vision" in constructor.parameters

    vision_client = FakeVisionClient(source_engine="granite_vision_3b", profile_name="granite")
    source = _source_with_page_image()
    gateway = ModelRoutingExtractionGateway(
        deterministic=RecordingDeterministicGateway(),
        vision=GraniteVisionExtractionGateway(client=vision_client),
    )

    result = gateway.extract(
        source,
        schema_name="invoice",
        route_profile="docling_plus_structured_extraction",
        semantic_task=_invoice_semantic_task(source),
    )

    assert result.route.source_engine == "granite_vision_3b"
    assert result.normalization_json["lane"] == VISION_LANE_NAME
    assert result.normalization_json["visionProvider"] == GRANITE_VISION_PROVIDER
    assert vision_client.request is not None


def test_qwen_vision_fallback_flag_routes_text_lane_abstention_to_qwen() -> None:
    source = _source_with_readable_kvp_text()
    granite = RecordingVisionGateway(source_engine="granite_vision_3b", provider="granite")
    qwen = RecordingVisionGateway(source_engine="qwen3_vl_8b", provider=QWEN_VISION_PROVIDER)
    gateway = ModelRoutingExtractionGateway(
        deterministic=RecordingDeterministicGateway(),
        vision=granite,
        qwen_vision=qwen,
        qwen_vision_fallback_enabled=True,
        text_lane_kvp=TextLaneKvpExtractionGateway(selector=NoMatchSpanSelector()),
    )

    result = gateway.extract(
        source,
        schema_name="document_observation",
        route_profile="docling_plus_structured_extraction",
        semantic_task=_kvp_semantic_task(source),
    )

    assert granite.calls == 0
    assert qwen.calls == 1
    assert result.route.source_engine == "qwen3_vl_8b"
    assert result.normalization_json["lane"] == VISION_LANE_NAME
    assert result.normalization_json["visionProvider"] == QWEN_VISION_PROVIDER
    assert str(result.normalization_json["laneEligibility"]).startswith(
        "text_lane_abstained:all_keys_unmatched"
    )


def test_qwen_vision_fallback_flag_routes_difficult_page_to_qwen() -> None:
    source = _source_with_page_image()
    granite = RecordingVisionGateway(source_engine="granite_vision_3b", provider="granite")
    qwen = RecordingVisionGateway(source_engine="qwen3_vl_8b", provider=QWEN_VISION_PROVIDER)
    gateway = ModelRoutingExtractionGateway(
        deterministic=RecordingDeterministicGateway(),
        vision=granite,
        qwen_vision=qwen,
        qwen_vision_fallback_enabled=True,
        text_lane_kvp=TextLaneKvpExtractionGateway(selector=NoMatchSpanSelector()),
    )

    result = gateway.extract(
        source,
        schema_name="document_observation",
        route_profile="docling_plus_structured_extraction",
        semantic_task=_kvp_semantic_task(source),
    )

    assert granite.calls == 0
    assert qwen.calls == 1
    assert result.route.source_engine == "qwen3_vl_8b"
    assert result.normalization_json["laneEligibility"] == "difficult_page:low_text_density"


def test_qwen_vision_fallback_flag_off_keeps_current_granite_fallback() -> None:
    source = _source_with_page_image()
    granite = RecordingVisionGateway(source_engine="granite_vision_3b", provider="granite")
    qwen = RecordingVisionGateway(source_engine="qwen3_vl_8b", provider=QWEN_VISION_PROVIDER)
    gateway = ModelRoutingExtractionGateway(
        deterministic=RecordingDeterministicGateway(),
        vision=granite,
        qwen_vision=qwen,
        qwen_vision_fallback_enabled=False,
        text_lane_kvp=TextLaneKvpExtractionGateway(selector=NoMatchSpanSelector()),
    )

    result = gateway.extract(
        source,
        schema_name="document_observation",
        route_profile="docling_plus_structured_extraction",
        semantic_task=_kvp_semantic_task(source),
    )

    assert granite.calls == 1
    assert qwen.calls == 0
    assert result.route.source_engine == "granite_vision_3b"


def test_routing_gateway_rejects_live_qwen_extraction_route() -> None:
    granite_client = FakeVisionClient(source_engine="granite_vision_3b", profile_name="granite")
    deterministic = RecordingDeterministicGateway()
    gateway = ModelRoutingExtractionGateway(
        deterministic=deterministic,
        granite=GraniteVisionExtractionGateway(client=granite_client),
    )

    with pytest.raises(ModelProtocolError, match="semantic-only"):
        gateway.extract(
            _source_with_page_image(),
            schema_name="invoice",
            route_profile="qwen_primary_review_required",
        )

    assert granite_client.request is None
    assert deterministic.called is False


@pytest.mark.parametrize(
    "route_profile",
    ["docling_plus_structured_extraction", "unrecognized_route"],
)
def test_routing_gateway_rejects_broad_live_structured_extraction_without_semantic_task(
    route_profile: str,
) -> None:
    granite_client = FakeVisionClient(source_engine="granite_vision_3b", profile_name="granite")
    deterministic = RecordingDeterministicGateway()
    gateway = ModelRoutingExtractionGateway(
        deterministic=deterministic,
        granite=GraniteVisionExtractionGateway(client=granite_client),
    )

    with pytest.raises(ModelProtocolError, match="semantic region task"):
        gateway.extract(
            _source_with_page_image(),
            schema_name="invoice",
            route_profile=route_profile,
        )

    assert granite_client.request is None
    assert deterministic.called is False


def test_routing_gateway_uses_granite_for_structured_route() -> None:
    granite_client = FakeVisionClient(source_engine="granite_vision_3b", profile_name="granite")
    source = _source_with_page_image()
    gateway = ModelRoutingExtractionGateway(
        deterministic=RecordingDeterministicGateway(),
        granite=GraniteVisionExtractionGateway(client=granite_client),
    )

    result = gateway.extract(
        source,
        schema_name="invoice",
        route_profile="docling_plus_structured_extraction",
        semantic_task=_invoice_semantic_task(source),
    )

    assert result.route.source_engine == "granite_vision_3b"
    assert granite_client.request is not None


def test_routing_structured_schemas_cover_every_target_extraction_schema() -> None:
    from lib.extraction.classification import TARGET_EXTRACTION_SCHEMAS
    from lib.extraction.gateways.routing import STRUCTURED_SCHEMAS

    assert STRUCTURED_SCHEMAS == frozenset(TARGET_EXTRACTION_SCHEMAS)
    assert "document_observation" in STRUCTURED_SCHEMAS


def test_routing_gateway_fails_closed_for_document_observation_on_unknown_route() -> None:
    granite_client = FakeVisionClient(source_engine="granite_vision_3b", profile_name="granite")
    deterministic = RecordingDeterministicGateway()
    gateway = ModelRoutingExtractionGateway(
        deterministic=deterministic,
        granite=GraniteVisionExtractionGateway(client=granite_client),
    )

    with pytest.raises(ModelProtocolError, match="semantic region task"):
        gateway.extract(
            _source_with_page_image(),
            schema_name="document_observation",
            route_profile="unrecognized_route",
        )

    assert granite_client.request is None
    assert deterministic.called is False


def test_default_extraction_gateway_remains_fixture_when_model_mode_is_fixture(monkeypatch) -> None:
    monkeypatch.setenv("STRUCTURA_MODEL_MODE", "fixture")
    get_settings.cache_clear()
    try:
        gateway = default_extraction_gateway()
    finally:
        get_settings.cache_clear()

    assert isinstance(gateway, DoclingHeuristicGateway)


def test_default_gateway_ignores_qwen_vision_profile_when_fallback_disabled(monkeypatch) -> None:
    monkeypatch.setenv("STRUCTURA_MODEL_MODE", "live")
    monkeypatch.setenv("STRUCTURA_QWEN_VISION_FALLBACK", "false")
    monkeypatch.setenv("STRUCTURA_QWEN_VISION_PROFILE", "not-a-real-profile:v1")
    get_settings.cache_clear()
    try:
        gateway = default_extraction_gateway()
    finally:
        get_settings.cache_clear()

    assert isinstance(gateway, ModelRoutingExtractionGateway)
    assert gateway.qwen_vision is None
