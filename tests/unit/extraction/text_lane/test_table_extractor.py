from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from uuid import uuid4

from lib.extraction.claims import claims_from_region_envelope
from lib.extraction.models import (
    ExtractionSourceDocument,
    ParsedPageText,
    ParsedTableText,
)
from lib.extraction.text_lane.column_labeling import ColumnLabeling
from lib.extraction.text_lane.table_extractor import (
    TEXT_LANE_TABLE_METHOD,
    extract_table_region,
)
from lib.extraction.text_lane.table_grid import TableGrid
from lib.semantic_annotations.models import SemanticExtractionTask, SemanticGroundingRef

FIXTURES = Path("tests/fixtures/text_lane")


def _table(fixture_name: str) -> ParsedTableText:
    payload = json.loads((FIXTURES / fixture_name).read_text())
    return ParsedTableText(
        table_id=uuid4(),
        page_number=payload["page_number"],
        table_index=payload["table_index"],
        table_json=payload["table_json"],
        element_id=uuid4(),
    )


def _source(table: ParsedTableText) -> ExtractionSourceDocument:
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
                page_number=table.page_number,
                text="Service invoice text",
                has_text_layer=True,
            )
        ],
        elements=[],
        tables=[table],
    )


def _task(
    table: ParsedTableText, semantic_type: str = "invoice_line_item_table"
) -> SemanticExtractionTask:
    return SemanticExtractionTask(
        region_id=uuid4(),
        annotation_id=uuid4(),
        document_id=uuid4(),
        semantic_type=semantic_type,
        granite_task="tables_json",
        target_schema="invoice",
        expected_fields=("description", "amount"),
        grounding=SemanticGroundingRef(kind="table", table_id=table.table_id),
    )


def _labeling(roles: dict[int, str]) -> ColumnLabeling:
    return ColumnLabeling(
        roles=roles,
        model_name="fake-qwen",
        model_version="test-1",
        prompt_version="text_lane_column_labeling.v1",
    )


def _service_extraction():
    table = _table("service_lines_grid.json")
    source = _source(table)
    task = _task(table)
    grid = TableGrid.from_parsed_table(table)
    assert grid is not None
    extraction = extract_table_region(
        source=source,
        semantic_task=task,
        grid=grid,
        labeling=_labeling({0: "description", 1: "quantity", 2: "amount"}),
        family="invoice",
        target_schema="invoice",
    )
    return extraction, source, task, grid


def test_line_items_are_verbatim_with_row_anchors() -> None:
    extraction, source, task, grid = _service_extraction()
    envelope = extraction.envelope
    assert extraction.line_item_count == 2
    assert extraction.totals_fact_count == 1
    first, second = envelope.line_items
    assert first.description == "600 mile run-in service"
    assert first.quantity == 1.0
    assert first.net_amount == 289.0
    assert second.description == "Rear tire replacement"
    assert second.net_amount == 412.5
    for item, expected_row in ((first, 1), (second, 2)):
        assert item.row_index == expected_row
        assert item.table_id == grid.table_id
        assert item.page_number == grid.page_number
        ref = item.evidence[0]
        assert ref.source_engine == "docling"
        assert ref.table_id == grid.table_id
        assert ref.row_index == expected_row
        assert ref.bbox is not None
        assert ref.document_id == str(source.document_id)
        assert ref.semantic_region_id == str(task.region_id)


def test_totals_row_emits_family_fact_not_line_item() -> None:
    extraction, *_ = _service_extraction()
    envelope = extraction.envelope
    assert [fact.name for fact in envelope.facts] == ["invoice.balance_due"]
    fact = envelope.facts[0]
    assert fact.value == {"amount": 701.5}
    assert fact.value_type == "money"
    assert fact.source_text == "701.50"
    descriptions = [item.description for item in envelope.line_items]
    assert "Balance due" not in descriptions


def test_envelope_mints_docling_claims_with_exact_anchors() -> None:
    extraction, source, *_ = _service_extraction()
    claims = claims_from_region_envelope(extraction.envelope)
    assert claims, "text-lane envelope must mint claims"
    assert {claim.source_engine for claim in claims} == {"docling"}
    assert all(claim.method == TEXT_LANE_TABLE_METHOD for claim in claims)
    assert all(claim.document_id == str(source.document_id) for claim in claims)
    # every claim carries a structural anchor by construction
    for claim in claims:
        assert claim.anchor.table_id is not None
        assert claim.anchor.page_number is not None
    line_groups = {
        claim.group_id for claim in claims if claim.canonical_key.startswith("invoice.line_item.")
    }
    assert len(line_groups) == 2
    totals = [claim for claim in claims if claim.canonical_key == "invoice.balance_due"]
    assert len(totals) == 1
    assert totals[0].typed_value == {"amount": 701.5}
    amounts = sorted(
        claim.typed_value["amount"]
        for claim in claims
        if claim.canonical_key == "invoice.line_item.amount"
    )
    assert amounts == [289.0, 412.5]


def test_repeatability_same_input_same_envelope_json() -> None:
    table = _table("service_lines_grid.json")
    source = _source(table)
    task = _task(table)
    grid = TableGrid.from_parsed_table(table)
    assert grid is not None
    labeling = _labeling({0: "description", 1: "quantity", 2: "amount"})
    first = extract_table_region(
        source=source,
        semantic_task=task,
        grid=grid,
        labeling=labeling,
        family="invoice",
        target_schema="invoice",
    )
    second = extract_table_region(
        source=source,
        semantic_task=task,
        grid=grid,
        labeling=labeling,
        family="invoice",
        target_schema="invoice",
    )
    assert first.envelope.model_dump(mode="json") == second.envelope.model_dump(mode="json")
    first_claims = [claim.claim_id for claim in claims_from_region_envelope(first.envelope)]
    second_claims = [claim.claim_id for claim in claims_from_region_envelope(second.envelope)]
    assert first_claims == second_claims


def test_unlabeled_and_unparseable_cells_are_skipped() -> None:
    table = _table("service_lines_grid.json")
    source = _source(table)
    task = _task(table)
    grid = TableGrid.from_parsed_table(table)
    assert grid is not None
    # only the description column is mapped; quantity/amount are ignored
    extraction = extract_table_region(
        source=source,
        semantic_task=task,
        grid=grid,
        labeling=_labeling({0: "description"}),
        family="invoice",
        target_schema="invoice",
    )
    # the totals row still resolves its amount from the rightmost money cell
    assert extraction.line_item_count == 2
    assert extraction.totals_fact_count == 1
    assert all(item.net_amount is None for item in extraction.envelope.line_items)


def test_escrow_grid_without_bboxes_still_anchors_by_table_row() -> None:
    table = _table("escrow_activity_grid.json")
    source = _source(table)
    task = _task(table, semantic_type="invoice_line_item_table")
    grid = TableGrid.from_parsed_table(table)
    assert grid is not None
    extraction = extract_table_region(
        source=source,
        semantic_task=task,
        grid=grid,
        labeling=_labeling({0: "description", 2: "amount"}),
        family="invoice",
        target_schema="invoice",
    )
    items = extraction.envelope.line_items
    assert items, "data rows extract even without cell bboxes"
    for item in items:
        ref = item.evidence[0]
        assert ref.bbox is None
        assert ref.table_id == grid.table_id
        assert ref.row_index is not None
    claims = claims_from_region_envelope(extraction.envelope)
    assert claims
    assert all(claim.anchor.row_index is not None for claim in claims)
