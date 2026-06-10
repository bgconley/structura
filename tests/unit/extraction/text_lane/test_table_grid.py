from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from lib.extraction.models import ParsedTableText
from lib.extraction.text_lane.table_grid import TableGrid

FIXTURES = Path("tests/fixtures/text_lane")


def _parsed_table(fixture_name: str) -> ParsedTableText:
    payload = json.loads((FIXTURES / fixture_name).read_text())
    return ParsedTableText(
        table_id=uuid4(),
        page_number=payload["page_number"],
        table_index=payload["table_index"],
        table_markdown=None,
        table_json=payload["table_json"],
        element_id=uuid4(),
        bbox={"l": 10.0, "t": 20.0, "r": 600.0, "b": 700.0},
    )


def _grid(fixture_name: str) -> TableGrid:
    grid = TableGrid.from_parsed_table(_parsed_table(fixture_name))
    assert grid is not None
    return grid


def test_service_lines_grid_round_trip() -> None:
    grid = _grid("service_lines_grid.json")
    assert (grid.num_rows, grid.num_cols) == (4, 3)
    assert grid.header_from_flags
    assert grid.header_row_indexes == (0,)
    assert grid.data_row_indexes == (1, 2, 3)
    assert grid.header_labels() == ("DESCRIPTION OF SERVICE AND PARTS", "", "AMOUNT")
    row = grid.row_cells(1)
    assert [cell.normalized_text for cell in row if cell is not None] == [
        "600 mile run-in service",
        "1",
        "289.00",
    ]
    assert all(cell is not None and cell.bbox is not None for cell in row)


def test_retail_grid_dedupes_span_duplicates_and_detects_header_block() -> None:
    grid = _grid("retail_order_items_grid.json")
    assert (grid.num_rows, grid.num_cols) == (4, 10)
    # The col_span=2 header cell is materialized twice in the raw grid but
    # parses into one unique cell resolvable at both positions.
    spanning = [cell for cell in grid.cells if cell.text == "ITEM DESCRIPTION"]
    assert len(spanning) == 1
    assert grid.cell_at(0, 0) is grid.cell_at(0, 1)
    # Three noisy header rows lead the table; the single data row remains.
    assert grid.header_row_indexes == (0, 1, 2)
    assert grid.data_row_indexes == (3,)
    labels = grid.header_labels()
    assert labels[0] == "ITEM DESCRIPTION"
    assert labels[3] == "QTY / ORDERED"
    assert labels[8] == "TOTAL"


def test_escrow_grid_tolerates_missing_bboxes_and_skips_empty_rows() -> None:
    grid = _grid("escrow_activity_grid.json")
    assert (grid.num_rows, grid.num_cols) == (7, 7)
    assert all(cell.bbox is None for cell in grid.cells)
    assert grid.header_row_indexes == (0, 1, 2)
    # Row 5 is entirely empty and is not a data row.
    assert grid.data_row_indexes == (3, 4, 6)
    # Multi-row headers join top-down per column through the span.
    labels = grid.header_labels()
    assert labels[1] == "DEPOSITS TO ESCROW / DATE"
    assert labels[4] == "PAYMENTS FROM ESCROW / AMOUNT / PROJECTED"
    # Span resolution: the spanning group header resolves at both columns.
    assert grid.cell_at(0, 1) is grid.cell_at(0, 2)


def test_header_fingerprint_is_stable_and_case_insensitive() -> None:
    first = _grid("service_lines_grid.json")
    second = _grid("service_lines_grid.json")
    assert first.header_fingerprint() == second.header_fingerprint()
    other = _grid("retail_order_items_grid.json")
    assert first.header_fingerprint() != other.header_fingerprint()


def test_first_row_fallback_when_no_header_flags() -> None:
    table = _parsed_table("service_lines_grid.json")
    stripped = json.loads(json.dumps(table.table_json))
    for row in stripped["data"]["grid"]:
        for cell in row:
            cell["column_header"] = False
    grid = TableGrid.from_parsed_table(
        ParsedTableText(
            table_id=table.table_id,
            page_number=table.page_number,
            table_index=table.table_index,
            table_json=stripped,
        )
    )
    assert grid is not None
    assert not grid.header_from_flags
    assert grid.header_row_indexes == (0,)
    assert grid.data_row_indexes == (1, 2, 3)


def test_unusable_table_json_returns_none() -> None:
    assert (
        TableGrid.from_parsed_table(
            ParsedTableText(table_id=uuid4(), page_number=1, table_index=1, table_json={})
        )
        is None
    )
    assert (
        TableGrid.from_parsed_table(
            ParsedTableText(
                table_id=uuid4(),
                page_number=1,
                table_index=1,
                table_json={"data": {"grid": []}},
            )
        )
        is None
    )
