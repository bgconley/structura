from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

from lib.extraction.models import (
    ExtractionSourceDocument,
    ParsedElementText,
    ParsedPageText,
    ParsedTableText,
)
from lib.extraction.text_lane.eligibility import text_lane_eligibility
from lib.semantic_annotations.models import SemanticExtractionTask, SemanticGroundingRef

FIXTURES = Path("tests/fixtures/text_lane")

_PAGE_TEXT = (
    "Invoice 6046058/1 for service and parts. "
    "600 mile run-in service 289.00. Rear tire replacement 412.50. "
    "Balance due 701.50. Please remit payment within 30 days of the invoice date."
)


def _table(page_number: int = 1, fixture: str = "service_lines_grid.json") -> ParsedTableText:
    payload = json.loads((FIXTURES / fixture).read_text())
    return ParsedTableText(
        table_id=uuid4(),
        page_number=page_number,
        table_index=payload["table_index"],
        table_markdown="| DESCRIPTION | | AMOUNT |\n| --- | --- | --- |\n| service | 1 | 289.00 |",
        table_json=payload["table_json"],
        element_id=uuid4(),
    )


def _source(
    *,
    tables: list[ParsedTableText],
    page_text: str = _PAGE_TEXT,
    has_text_layer: bool | None = True,
    page_metadata: dict[str, object] | None = None,
) -> ExtractionSourceDocument:
    return ExtractionSourceDocument(
        document_id=uuid4(),
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
                page_number=1,
                text=page_text,
                has_text_layer=has_text_layer,
                metadata=page_metadata or {},
            )
        ],
        elements=[
            ParsedElementText(
                element_id=uuid4(),
                page_number=1,
                ordinal=1,
                text=page_text,
            )
        ],
        tables=tables,
    )


def _task(
    table: ParsedTableText | None,
    *,
    semantic_type: str = "invoice_line_item_table",
    document_id: UUID | None = None,
) -> SemanticExtractionTask:
    grounding = (
        SemanticGroundingRef(kind="table", table_id=table.table_id)
        if table is not None
        else SemanticGroundingRef(kind="page", page_id=uuid4())
    )
    return SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=document_id or uuid4(),
        semantic_type=semantic_type,
        granite_task="tables_json",
        target_schema="invoice",
        expected_fields=("description", "amount"),
        grounding=grounding,
    )


def test_strong_table_on_text_page_is_text_lane() -> None:
    table = _table()
    decision = text_lane_eligibility(_source(tables=[table]), semantic_task=_task(table))
    assert decision.lane == "text"
    assert decision.reason == "strong_table_on_text_page"
    assert decision.table_id == str(table.table_id)
    assert decision.page_number == 1


def test_non_line_item_region_routes_to_vision() -> None:
    table = _table()
    decision = text_lane_eligibility(
        _source(tables=[table]),
        semantic_task=_task(table, semantic_type="payment_summary"),
    )
    assert decision.lane == "vision"
    assert decision.reason == "region_not_line_item_table"


def test_missing_table_grounding_routes_to_vision() -> None:
    table = _table()
    decision = text_lane_eligibility(_source(tables=[table]), semantic_task=_task(None))
    assert decision.lane == "vision"
    assert decision.reason == "no_grounded_docling_table"


def test_element_grounding_resolves_table() -> None:
    table = _table()
    task = SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=uuid4(),
        semantic_type="invoice_line_item_table",
        granite_task="tables_json",
        target_schema="invoice",
        expected_fields=(),
        grounding=SemanticGroundingRef(kind="element", element_id=table.element_id),
    )
    decision = text_lane_eligibility(_source(tables=[table]), semantic_task=task)
    assert decision.lane == "text"


def test_low_text_scan_page_routes_to_vision() -> None:
    table = _table()
    decision = text_lane_eligibility(
        _source(tables=[table], page_text="scan"),
        semantic_task=_task(table),
    )
    assert decision.lane == "vision"
    assert decision.reason.startswith("difficult_page:")
    assert "low_text_density" in decision.reason


def test_missing_text_layer_routes_to_vision() -> None:
    table = _table()
    decision = text_lane_eligibility(
        _source(tables=[table], has_text_layer=False),
        semantic_task=_task(table),
    )
    assert decision.lane == "vision"
    assert "missing_text_layer" in decision.reason


def test_handwriting_metadata_routes_to_vision() -> None:
    table = _table()
    decision = text_lane_eligibility(
        _source(tables=[table], page_metadata={"hasHandwriting": True}),
        semantic_task=_task(table),
    )
    assert decision.lane == "vision"
    assert "handwriting" in decision.reason


def test_table_without_grid_routes_to_vision() -> None:
    table = ParsedTableText(
        table_id=uuid4(),
        page_number=1,
        table_index=1,
        table_markdown="| a | b |\n| --- | --- |\n| 1 | 2 |",
        table_json={},
    )
    decision = text_lane_eligibility(_source(tables=[table]), semantic_task=_task(table))
    assert decision.lane == "vision"
    assert decision.reason == "table_grid_missing"


def test_weak_table_signal_routes_to_vision() -> None:
    payload = json.loads((FIXTURES / "service_lines_grid.json").read_text())
    table = ParsedTableText(
        table_id=uuid4(),
        page_number=1,
        table_index=1,
        table_markdown="| only-header |",
        table_json={
            "data": {
                "num_rows": 2,
                "num_cols": 2,
                "grid": [
                    payload["table_json"]["data"]["grid"][0][:2],
                    payload["table_json"]["data"]["grid"][1][:2],
                ],
            }
        },
    )
    decision = text_lane_eligibility(_source(tables=[table]), semantic_task=_task(table))
    assert decision.lane == "vision"
    assert decision.reason.startswith("table_signal_")
