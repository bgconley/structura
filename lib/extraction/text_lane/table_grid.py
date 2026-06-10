"""Typed access to the Docling table cell grid persisted in table_json.

`document_tables.table_json["data"]["grid"]` materializes every cell per
occupied position: a cell spanning N columns appears N times with identical
start/end offsets. This module parses that grid once into unique typed cells,
resolves spans through positional accessors, and detects the leading header
block from Docling `column_header` flags (first-row fallback when a table
carries no flags at all, e.g. two-column description/amount tables).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from lib.extraction.model_output_value_parsing import parse_decimal_text
from lib.extraction.models import ParsedTableText


@dataclass(frozen=True)
class TableGridCell:
    text: str
    row: int
    col: int
    row_span: int
    col_span: int
    bbox: tuple[float, float, float, float] | None
    column_header: bool
    row_header: bool
    row_section: bool

    @property
    def normalized_text(self) -> str:
        return " ".join(self.text.split())


@dataclass(frozen=True)
class TableGrid:
    table_id: str
    page_number: int
    element_id: str | None
    table_bbox: Any | None
    num_rows: int
    num_cols: int
    cells: tuple[TableGridCell, ...]
    header_from_flags: bool

    @classmethod
    def from_parsed_table(cls, table: ParsedTableText) -> TableGrid | None:
        data = table.table_json.get("data")
        if not isinstance(data, dict):
            return None
        grid = data.get("grid")
        if not isinstance(grid, list) or not grid:
            return None
        cells: dict[tuple[int, int], TableGridCell] = {}
        max_row = 0
        max_col = 0
        for row in grid:
            if not isinstance(row, list):
                return None
            for raw in row:
                if not isinstance(raw, dict):
                    continue
                cell = _cell(raw)
                if cell is None:
                    continue
                cells.setdefault((cell.row, cell.col), cell)
                max_row = max(max_row, cell.row + cell.row_span)
                max_col = max(max_col, cell.col + cell.col_span)
        if not cells:
            return None
        num_rows = _positive_int(data.get("num_rows")) or max_row
        num_cols = _positive_int(data.get("num_cols")) or max_col
        header_from_flags = any(cell.column_header for cell in cells.values())
        return cls(
            table_id=str(table.table_id),
            page_number=table.page_number,
            element_id=str(table.element_id) if table.element_id is not None else None,
            table_bbox=table.bbox,
            num_rows=num_rows,
            num_cols=num_cols,
            cells=tuple(cells[key] for key in sorted(cells)),
            header_from_flags=header_from_flags,
        )

    @cached_property
    def _cells_by_position(self) -> dict[tuple[int, int], TableGridCell]:
        positions: dict[tuple[int, int], TableGridCell] = {}
        for cell in self.cells:
            for row in range(cell.row, cell.row + cell.row_span):
                for col in range(cell.col, cell.col + cell.col_span):
                    positions.setdefault((row, col), cell)
        return positions

    def cell_at(self, row: int, col: int) -> TableGridCell | None:
        """Resolve the cell occupying (row, col), following row/col spans."""
        return self._cells_by_position.get((row, col))

    def row_cells(self, row: int) -> tuple[TableGridCell | None, ...]:
        return tuple(self.cell_at(row, col) for col in range(self.num_cols))

    @cached_property
    def header_row_indexes(self) -> tuple[int, ...]:
        """Leading run of rows that contain any Docling column_header flag.

        Docling flags multi-row headers inconsistently (partial rows, spill
        into a third row), so the block is the maximal leading run of rows
        with at least one flagged cell. Tables with no flags anywhere fall
        back to treating the first row as the header only when it looks like
        one: a first row already carrying numeric values beyond the first
        column (receipt-style "ITEM | 2.25" grids) is data, not a header.
        """
        if not self.header_from_flags:
            if not self.num_rows:
                return ()
            return () if self._row_has_numeric_value(0) else (0,)
        indexes: list[int] = []
        for row in range(self.num_rows):
            cells = [cell for cell in self.row_cells(row) if cell is not None]
            if cells and any(cell.column_header for cell in cells):
                indexes.append(row)
            else:
                break
        return tuple(indexes) or ((0,) if self.num_rows else ())

    @cached_property
    def data_row_indexes(self) -> tuple[int, ...]:
        """Rows after the header block with content, excluding Docling
        row_section bands (e.g. "Labor" / "Parts" group headings)."""
        header = set(self.header_row_indexes)
        indexes: list[int] = []
        for row in range(self.num_rows):
            if row in header:
                continue
            cells = [
                cell for cell in self.row_cells(row) if cell is not None and cell.normalized_text
            ]
            if not cells:
                continue
            if all(cell.row_section for cell in cells):
                continue
            indexes.append(row)
        return tuple(indexes)

    def _row_has_numeric_value(self, row: int) -> bool:
        for col in range(1, self.num_cols):
            cell = self.cell_at(row, col)
            if cell is None:
                continue
            text = cell.normalized_text
            if text and parse_decimal_text(text) is not None:
                return True
        return False

    def header_labels(self) -> tuple[str, ...]:
        """Per-column header text, joining multi-row headers top-down."""
        labels: list[str] = []
        for col in range(self.num_cols):
            seen: list[str] = []
            for row in self.header_row_indexes:
                cell = self.cell_at(row, col)
                if cell is None:
                    continue
                text = cell.normalized_text
                if text and text not in seen:
                    seen.append(text)
            labels.append(" / ".join(seen))
        return tuple(labels)

    def header_fingerprint(self) -> str:
        """Stable identity for (column count + normalized header labels).

        Used to cache model column-role labels so identical table shapes
        never re-call the model.
        """
        payload = {
            "num_cols": self.num_cols,
            "labels": [label.casefold() for label in self.header_labels()],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _cell(raw: dict[str, Any]) -> TableGridCell | None:
    row = _offset(raw.get("start_row_offset_idx"))
    col = _offset(raw.get("start_col_offset_idx"))
    if row is None or col is None:
        return None
    return TableGridCell(
        text=str(raw.get("text") or ""),
        row=row,
        col=col,
        row_span=_positive_int(raw.get("row_span")) or 1,
        col_span=_positive_int(raw.get("col_span")) or 1,
        bbox=_cell_bbox(raw.get("bbox")),
        column_header=bool(raw.get("column_header")),
        row_header=bool(raw.get("row_header")),
        row_section=bool(raw.get("row_section")),
    )


def _cell_bbox(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, dict):
        return None
    try:
        return (
            float(value["l"]),
            float(value["t"]),
            float(value["r"]),
            float(value["b"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _offset(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if not isinstance(value, int):
        return None
    return value if value >= 0 else None


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if not isinstance(value, int):
        return None
    return value if value > 0 else None
