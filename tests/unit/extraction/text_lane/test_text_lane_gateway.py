from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from lib.extraction.gateways.routing import ModelRoutingExtractionGateway
from lib.extraction.models import (
    ExtractionSourceDocument,
    GatewayExtraction,
    ModelRoute,
    ParsedElementText,
    ParsedPageText,
    ParsedTableText,
    PersistedExtraction,
)
from lib.extraction.service import ExtractionService
from lib.extraction.text_lane.column_labeling import (
    ColumnLabeling,
    ColumnLabelingValidationError,
)
from lib.extraction.text_lane.gateway import (
    TextLaneAbstention,
    TextLaneTableExtractionGateway,
)
from lib.semantic_annotations.models import SemanticExtractionTask, SemanticGroundingRef

FIXTURES = Path("tests/fixtures/text_lane")

_PAGE_TEXT = (
    "Invoice 6046058/1 for service and parts. "
    "600 mile run-in service 289.00. Rear tire replacement 412.50. "
    "Balance due 701.50. Please remit payment within 30 days of the invoice date."
)


class _StaticLabeler:
    def __init__(self, roles: dict[int, str]) -> None:
        self.roles = roles
        self.calls = 0

    def label_columns(self, *, family: str, grid) -> ColumnLabeling:  # noqa: ANN001
        del family, grid
        self.calls += 1
        return ColumnLabeling(
            roles=self.roles,
            model_name="fake-qwen",
            model_version="test-1",
            prompt_version="text_lane_column_labeling.v1",
        )


class _FakeGranite:
    def __init__(self) -> None:
        self.calls = 0

    def extract(
        self,
        source: ExtractionSourceDocument,
        *,
        schema_name: str,
        route_profile: str,
        semantic_task: SemanticExtractionTask | None = None,
    ) -> GatewayExtraction:
        del source, semantic_task
        self.calls += 1
        return GatewayExtraction(
            schema_name=schema_name,
            schema_version="v1",
            route=ModelRoute(
                source_engine="granite_vision_3b",
                model_name="granite",
                model_version="test",
                prompt_version="granite-test",
                route_profile=route_profile,
            ),
            normalized_json={"schema_name": schema_name},
            raw_output_json={},
        )


class _FakeDeterministic:
    def extract(self, source, **kwargs):  # noqa: ANN001, ANN003
        raise AssertionError("deterministic gateway should not run in these tests")


class _InvalidLabeler:
    def label_columns(self, *, family: str, grid) -> ColumnLabeling:  # noqa: ANN001
        del family, grid
        raise ColumnLabelingValidationError("missing_column_index:2")


def _table(fixture_name: str = "service_lines_grid.json") -> ParsedTableText:
    payload = json.loads((FIXTURES / fixture_name).read_text())
    return ParsedTableText(
        table_id=uuid4(),
        page_number=payload["page_number"],
        table_index=payload["table_index"],
        table_markdown="| DESCRIPTION | | AMOUNT |\n| --- | --- | --- |\n| svc | 1 | 289.00 |",
        table_json=payload["table_json"],
        element_id=uuid4(),
    )


def _source(table: ParsedTableText, document_id: UUID | None = None) -> ExtractionSourceDocument:
    return ExtractionSourceDocument(
        document_id=document_id or uuid4(),
        household_id=uuid4(),
        title="Service invoice",
        original_filename="service-invoice.pdf",
        mime_type="application/pdf",
        family="invoice",
        subtype=None,
        sensitivity="standard",
        document_date=date(2026, 6, 1),
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[
            ParsedPageText(
                page_id=uuid4(),
                page_number=table.page_number,
                text=_PAGE_TEXT,
                has_text_layer=True,
            )
        ],
        elements=[ParsedElementText(element_id=uuid4(), page_number=1, ordinal=1, text=_PAGE_TEXT)],
        tables=[table],
    )


def _task(
    table: ParsedTableText,
    *,
    semantic_type: str = "invoice_line_item_table",
    document_id: UUID | None = None,
) -> SemanticExtractionTask:
    return SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=document_id or uuid4(),
        semantic_type=semantic_type,
        granite_task="tables_json",
        target_schema="invoice",
        expected_fields=("description", "amount"),
        grounding=SemanticGroundingRef(kind="table", table_id=table.table_id),
    )


def _routing(
    labeler_roles: dict[int, str] | None,
) -> tuple[ModelRoutingExtractionGateway, _FakeGranite]:
    granite = _FakeGranite()
    text_lane = (
        TextLaneTableExtractionGateway(labeler=_StaticLabeler(labeler_roles))
        if labeler_roles is not None
        else None
    )
    gateway = ModelRoutingExtractionGateway(
        deterministic=_FakeDeterministic(),
        granite=granite,
        text_lane_tables=text_lane,
    )
    return gateway, granite


def test_eligible_line_item_region_routes_to_text_lane() -> None:
    table = _table()
    gateway, granite = _routing({0: "description", 1: "quantity", 2: "amount"})
    result = gateway.extract(
        _source(table),
        schema_name="invoice",
        route_profile="docling_plus_structured_extraction",
        semantic_task=_task(table),
    )
    assert granite.calls == 0
    assert result.route.source_engine == "docling"
    assert result.normalization_json["lane"] == "text"
    assert result.normalization_json["laneEligibility"] == "usable_grid_on_text_page"
    assert isinstance(result.normalization_json["regionEnvelope"], dict)
    assert result.model_output_schema_name == "text_lane_table.v1"
    assert result.normalized_json["schema_name"] == "invoice"
    line_items = result.normalized_json.get("line_items")
    assert isinstance(line_items, list) and len(line_items) == 2


def test_ineligible_region_falls_back_to_vision_with_lane_telemetry() -> None:
    table = _table()
    gateway, granite = _routing({0: "description", 1: "quantity", 2: "amount"})
    result = gateway.extract(
        _source(table),
        schema_name="invoice",
        route_profile="docling_plus_structured_extraction",
        semantic_task=_task(table, semantic_type="payment_summary"),
    )
    assert granite.calls == 1
    assert result.normalization_json["lane"] == "vision"
    assert result.normalization_json["laneEligibility"] == "region_not_line_item_table"


def test_text_lane_abstention_falls_back_to_vision() -> None:
    table = _table()
    gateway, granite = _routing({0: "ignore", 1: "ignore", 2: "ignore"})
    result = gateway.extract(
        _source(table),
        schema_name="invoice",
        route_profile="docling_plus_structured_extraction",
        semantic_task=_task(table),
    )
    assert granite.calls == 1
    assert result.normalization_json["lane"] == "vision"
    assert str(result.normalization_json["laneEligibility"]).startswith(
        "text_lane_abstained:all_columns_labeled_ignore"
    )


def test_column_labeling_validation_abstains_to_vision() -> None:
    table = _table()
    granite = _FakeGranite()
    text_lane = TextLaneTableExtractionGateway(labeler=_InvalidLabeler())
    gateway = ModelRoutingExtractionGateway(
        deterministic=_FakeDeterministic(),
        granite=granite,
        text_lane_tables=text_lane,
    )

    result = gateway.extract(
        _source(table),
        schema_name="invoice",
        route_profile="docling_plus_structured_extraction",
        semantic_task=_task(table),
    )

    assert granite.calls == 1
    assert result.normalization_json["lane"] == "vision"
    assert str(result.normalization_json["laneEligibility"]).startswith(
        "text_lane_abstained:column_labeling_failed:missing_column_index:2"
    )


def test_flag_off_leaves_vision_result_untouched() -> None:
    table = _table()
    gateway, granite = _routing(None)
    result = gateway.extract(
        _source(table),
        schema_name="invoice",
        route_profile="docling_plus_structured_extraction",
        semantic_task=_task(table),
    )
    assert granite.calls == 1
    assert "lane" not in result.normalization_json


def test_gateway_abstains_without_description_column() -> None:
    table = _table()
    text_lane = TextLaneTableExtractionGateway(
        labeler=_StaticLabeler({0: "ignore", 1: "quantity", 2: "amount"})
    )
    with pytest.raises(TextLaneAbstention) as excinfo:
        text_lane.extract(
            _source(table),
            schema_name="invoice",
            route_profile="docling_plus_structured_extraction",
            semantic_task=_task(table),
        )
    assert excinfo.value.reason == "no_description_column"


def test_service_routes_text_lane_validation_and_coverage() -> None:
    table = _table()
    document_id = uuid4()
    source = _source(table, document_id=document_id)
    task = _task(table, document_id=document_id)
    text_lane = TextLaneTableExtractionGateway(
        labeler=_StaticLabeler({0: "description", 1: "quantity", 2: "amount"})
    )
    routing = ModelRoutingExtractionGateway(
        deterministic=_FakeDeterministic(),
        granite=_FakeGranite(),
        text_lane_tables=text_lane,
    )
    captured: dict[str, object] = {}

    def _persister(gateway_result, **kwargs):  # noqa: ANN001, ANN003
        captured["gateway_result"] = gateway_result
        captured.update(kwargs)
        return PersistedExtraction(
            extraction_id=uuid4(),
            review_status="needs_review",
            candidate_count=0,
            canonical_count=0,
            review_task_count=0,
        )

    service = ExtractionService(
        gateway=routing,
        jobs=None,  # type: ignore[arg-type]
        source_loader=lambda _document_id: source,
        semantic_task_loader=lambda _region_id: task,
        persister=_persister,
    )
    service.extract_document(
        document_id,
        schema_name="invoice",
        semantic_region_id=task.region_id,
    )
    validation = captured["validation"]
    checks = {check["code"]: check["status"] for check in validation.checks}
    assert validation.needs_review is True
    assert checks.get("region_scope.text_lane_extraction") == "passed"
    assert "region_scope.text_lane_review_required" in checks
    assert "region_scope.model_candidate_review_required" not in checks
    gateway_result = captured["gateway_result"]
    coverage = gateway_result.normalization_json.get("expected_field_coverage")
    assert isinstance(coverage, dict)
    line_item_candidates = captured["line_item_candidates"]
    assert len(line_item_candidates) == 2
    assert all(candidate.status == "needs_review" for candidate in line_item_candidates)
    field_candidates = captured["field_candidates"]
    assert [candidate.field_path for candidate in field_candidates] == ["invoice.balance_due"]
