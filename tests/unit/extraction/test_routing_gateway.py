from __future__ import annotations

import inspect
from dataclasses import dataclass
from uuid import uuid4

import pytest

from lib.config import get_settings
from lib.extraction.gateway import DoclingHeuristicGateway
from lib.extraction.gateways.granite_vision import GraniteVisionExtractionGateway
from lib.extraction.gateways.routing import (
    ModelRoutingExtractionGateway,
    default_extraction_gateway,
)
from lib.extraction.models import ExtractionSourceDocument
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


def test_live_routing_gateway_has_no_qwen_extraction_dependency() -> None:
    constructor = inspect.signature(ModelRoutingExtractionGateway)
    routing_source = inspect.getsource(ModelRoutingExtractionGateway)

    assert "qwen" not in constructor.parameters
    assert "QwenVLExtractionGateway" not in routing_source


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
