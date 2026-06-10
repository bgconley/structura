"""Regression coverage for the 2026-06-10 adversarial review findings.

Each test pins a confirmed pre-gate defect: substring totals matching eating
line items, leftmost-money totals values capturing rates, EOB totals rows
double-counting as service lines, row_section bands becoming line items,
first-row header fallback eating flag-less data rows, the per-instance label
cache, the wrong medical_eob 'amount' gloss, and missing money-column
screens.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

import pytest

from lib.extraction.claims import claims_from_region_envelope
from lib.extraction.models import (
    ExtractionSourceDocument,
    ParsedPageText,
    ParsedTableText,
)
from lib.extraction.text_lane.column_labeling import (
    ColumnLabeling,
    column_labeling_prompt,
    line_item_roles,
)
from lib.extraction.text_lane.gateway import (
    TextLaneAbstention,
    TextLaneTableExtractionGateway,
)
from lib.extraction.text_lane.table_extractor import extract_table_region
from lib.extraction.text_lane.table_grid import TableGrid
from lib.semantic_annotations.models import SemanticExtractionTask, SemanticGroundingRef


def _cell(
    text: str,
    row: int,
    col: int,
    *,
    ch: bool = False,
    section: bool = False,
) -> dict[str, Any]:
    return {
        "text": text,
        "row_span": 1,
        "col_span": 1,
        "start_row_offset_idx": row,
        "end_row_offset_idx": row + 1,
        "start_col_offset_idx": col,
        "end_col_offset_idx": col + 1,
        "column_header": ch,
        "row_header": False,
        "row_section": section,
        "fillable": False,
        "bbox": {
            "l": 36.0 + col * 110.0,
            "t": 100.0 + row * 18.0,
            "r": 136.0 + col * 110.0,
            "b": 112.0 + row * 18.0,
            "coord_origin": "TOPLEFT",
        },
    }


def _table(rows: list[list[dict[str, Any]]]) -> ParsedTableText:
    return ParsedTableText(
        table_id=uuid4(),
        page_number=1,
        table_index=1,
        table_markdown="| a | b |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |",
        table_json={"data": {"num_rows": len(rows), "num_cols": len(rows[0]), "grid": rows}},
        element_id=uuid4(),
    )


def _grid(rows: list[list[dict[str, Any]]]) -> TableGrid:
    grid = TableGrid.from_parsed_table(_table(rows))
    assert grid is not None
    return grid


def _source(table: ParsedTableText) -> ExtractionSourceDocument:
    return ExtractionSourceDocument(
        document_id=uuid4(),
        household_id=uuid4(),
        title="doc",
        original_filename="doc.pdf",
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
                text="x" * 200,
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
        expected_fields=(),
        grounding=SemanticGroundingRef(kind="table", table_id=table.table_id),
    )


def _labeling(roles: dict[int, str]) -> ColumnLabeling:
    return ColumnLabeling(
        roles=roles,
        model_name="fake",
        model_version="t",
        prompt_version="text_lane_column_labeling.v1",
    )


def _extract(
    rows: list[list[dict[str, Any]]],
    roles: dict[int, str],
    *,
    family: str = "invoice",
):
    table = _table(rows)
    grid = TableGrid.from_parsed_table(table)
    assert grid is not None
    return extract_table_region(
        source=_source(table),
        semantic_task=_task(table),
        grid=grid,
        labeling=_labeling(roles),
        family=family,
        target_schema="invoice" if family != "medical_eob" else "medical_eob",
    )


def test_totals_words_inside_item_descriptions_stay_line_items() -> None:
    rows = [
        [
            _cell("Description", 0, 0, ch=True),
            _cell("Qty", 0, 1, ch=True),
            _cell("Amount", 0, 2, ch=True),
        ],
        [_cell("Taxi to airport", 1, 0), _cell("1", 1, 1), _cell("45.00", 1, 2)],
        [_cell("Total Cereal", 2, 0), _cell("1", 2, 1), _cell("5.99", 2, 2)],
        [_cell("Tip-top widget", 3, 0), _cell("2", 3, 1), _cell("4.00", 3, 2)],
        [_cell("Tax", 4, 0), _cell("", 4, 1), _cell("4.40", 4, 2)],
    ]
    extraction = _extract(rows, {0: "description", 1: "quantity", 2: "amount"})
    descriptions = [item.description for item in extraction.envelope.line_items]
    assert descriptions == ["Taxi to airport", "Total Cereal", "Tip-top widget"]
    assert [fact.name for fact in extraction.envelope.facts] == ["invoice.tax_total"]
    assert extraction.envelope.facts[0].value == {"amount": 4.4}


def test_totals_value_prefers_amount_column_over_rate_column() -> None:
    rows = [
        [
            _cell("Description", 0, 0, ch=True),
            _cell("Rate", 0, 1, ch=True),
            _cell("Amount", 0, 2, ch=True),
        ],
        [_cell("Consulting", 1, 0), _cell("150.00", 1, 1), _cell("300.00", 1, 2)],
        [_cell("Sales Tax", 2, 0), _cell("8.25", 2, 1), _cell("24.75", 2, 2)],
    ]
    extraction = _extract(rows, {0: "description", 1: "unit_price", 2: "amount"})
    facts = {fact.name: fact.value for fact in extraction.envelope.facts}
    assert facts == {"invoice.tax_total": {"amount": 24.75}}


def test_unmapped_totals_rows_are_suppressed_not_line_itemized() -> None:
    rows = [
        [
            _cell("Service", 0, 0, ch=True),
            _cell("Billed", 0, 1, ch=True),
            _cell("Allowed", 0, 2, ch=True),
            _cell("Plan Paid", 0, 3, ch=True),
            _cell("Patient", 0, 4, ch=True),
        ],
        [
            _cell("MRI lumbar spine", 1, 0),
            _cell("280.00", 1, 1),
            _cell("210.00", 1, 2),
            _cell("168.00", 1, 3),
            _cell("42.00", 1, 4),
        ],
        [
            _cell("Totals", 2, 0),
            _cell("280.00", 2, 1),
            _cell("210.00", 2, 2),
            _cell("168.00", 2, 3),
            _cell("42.00", 2, 4),
        ],
    ]
    extraction = _extract(
        rows,
        {
            0: "description",
            1: "gross_amount",
            2: "allowed_amount",
            3: "plan_paid",
            4: "amount",
        },
        family="medical_eob",
    )
    assert extraction.line_item_count == 1
    assert extraction.suppressed_totals_row_count == 1
    assert extraction.totals_fact_count == 0
    claims = claims_from_region_envelope(extraction.envelope)
    descriptions = {
        claim.raw_value
        for claim in claims
        if claim.canonical_key == "medical_eob.line_item.description"
    }
    assert descriptions == {'"MRI lumbar spine"'}


def test_row_section_bands_are_not_data_rows() -> None:
    rows = [
        [_cell("Description", 0, 0, ch=True), _cell("Amount", 0, 1, ch=True)],
        [_cell("Labor", 1, 0, section=True), _cell("", 1, 1, section=True)],
        [_cell("Replace brake pads", 2, 0), _cell("220.00", 2, 1)],
    ]
    grid = _grid(rows)
    assert grid.data_row_indexes == (2,)
    extraction = _extract(rows, {0: "description", 1: "amount"})
    assert [item.description for item in extraction.envelope.line_items] == ["Replace brake pads"]


def test_flagless_first_row_with_values_is_data_not_header() -> None:
    rows = [
        [_cell("GROCERY HRD SHRP CHDR", 0, 0), _cell("2.25", 0, 1)],
        [_cell("BANANAS", 1, 0), _cell("0.89", 1, 1)],
    ]
    grid = _grid(rows)
    assert not grid.header_from_flags
    assert grid.header_row_indexes == ()
    assert grid.data_row_indexes == (0, 1)


def test_flagless_textual_first_row_remains_header_fallback() -> None:
    rows = [
        [_cell("Description", 0, 0), _cell("Amount", 0, 1)],
        [_cell("Bananas", 1, 0), _cell("0.89", 1, 1)],
    ]
    grid = _grid(rows)
    assert grid.header_row_indexes == (0,)
    assert grid.data_row_indexes == (1,)


def test_label_cache_is_shared_across_labeler_instances() -> None:
    import json as _json

    from lib.extraction.text_lane.column_labeling import (
        LiveColumnRoleLabeler,
        clear_column_label_cache,
    )
    from lib.model_runtime.contracts import TextGenerateRequest, TextGenerateResponse

    clear_column_label_cache()

    class _Profile:
        name = "qwen3-vl-8b-fp8-semantic:v1"

    class _Client:
        profile = _Profile()
        calls = 0

        def generate(self, request: TextGenerateRequest) -> TextGenerateResponse:
            type(self).calls += 1
            payload = {
                "columns": [
                    {"column_index": 0, "role": "description"},
                    {"column_index": 1, "role": "amount"},
                ]
            }
            return TextGenerateResponse(
                profile_name=request.profile_name,
                model_name="fake",
                model_version="t",
                source_engine="qwen3_vl_8b",
                prompt_version=request.prompt_version,
                raw_text=_json.dumps(payload),
                normalized_json=payload,
                prompt_sha256="0" * 64,
                latency_ms=1,
                structured_output_used=True,
            )

    rows = [
        [_cell("Description", 0, 0, ch=True), _cell("Amount", 0, 1, ch=True)],
        [_cell("Bananas", 1, 0), _cell("0.89", 1, 1)],
    ]
    grid = _grid(rows)
    first = LiveColumnRoleLabeler(client=_Client())  # type: ignore[arg-type]
    second = LiveColumnRoleLabeler(client=_Client())  # type: ignore[arg-type]
    try:
        assert not first.label_columns(family="invoice", grid=grid).from_cache
        # a brand-new labeler instance (fresh per-job service) must still hit
        assert second.label_columns(family="invoice", grid=grid).from_cache
        assert _Client.calls == 1
    finally:
        clear_column_label_cache()


def test_medical_eob_prompt_gloss_matches_registry_meaning() -> None:
    rows = [
        [
            _cell("Service", 0, 0, ch=True),
            _cell("Billed", 0, 1, ch=True),
            _cell("Patient", 0, 2, ch=True),
        ],
        [_cell("MRI", 1, 0), _cell("280.00", 1, 1), _cell("42.00", 1, 2)],
    ]
    grid = _grid(rows)
    prompt = column_labeling_prompt(
        family="medical_eob", grid=grid, roles=line_item_roles("medical_eob")
    )
    assert "patient responsibility" in prompt
    assert "extended/net total" not in prompt
    invoice_prompt = column_labeling_prompt(
        family="invoice", grid=grid, roles=line_item_roles("invoice")
    )
    assert "extended/net total" in invoice_prompt


def test_gateway_abstains_without_money_column_and_on_sparse_money() -> None:
    class _Labeler:
        def __init__(self, roles: dict[int, str]) -> None:
            self.roles = roles

        def label_columns(self, *, family: str, grid: TableGrid) -> ColumnLabeling:
            del family, grid
            return _labeling(self.roles)

    no_money_rows = [
        [_cell("Description", 0, 0, ch=True), _cell("Code", 0, 1, ch=True)],
        [_cell("Bananas", 1, 0), _cell("B-1", 1, 1)],
    ]
    table = _table(no_money_rows)
    gateway = TextLaneTableExtractionGateway(labeler=_Labeler({0: "description", 1: "code"}))
    with pytest.raises(TextLaneAbstention) as no_money:
        gateway.extract(
            _source(table),
            schema_name="invoice",
            route_profile="docling_plus_structured_extraction",
            semantic_task=_task(table),
        )
    assert no_money.value.reason == "no_money_column"

    sparse_rows = [
        [_cell("Description", 0, 0, ch=True), _cell("Amount", 0, 1, ch=True)],
        [_cell("Tripod with fluid head", 1, 0), _cell("", 1, 1)],
        [_cell("Spare plate", 2, 0), _cell("", 2, 1)],
        [_cell("Strap", 3, 0), _cell("12.00", 3, 1)],
    ]
    sparse_table = _table(sparse_rows)
    sparse_gateway = TextLaneTableExtractionGateway(
        labeler=_Labeler({0: "description", 1: "amount"})
    )
    with pytest.raises(TextLaneAbstention) as sparse:
        sparse_gateway.extract(
            _source(sparse_table),
            schema_name="invoice",
            route_profile="docling_plus_structured_extraction",
            semantic_task=_task(sparse_table),
        )
    assert sparse.value.reason == "money_columns_sparse"
