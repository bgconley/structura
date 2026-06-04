from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from lib.extraction.models import ParsedTableText

DOCLING_TABLE_LABELER_ROUTE = "docling_table_plus_granite_labeler"
GRANITE_REGION_CONTEXT_ROUTE = "granite_region_with_docling_context"
GRANITE_FULL_PAGE_REVIEW_ROUTE = "granite_full_page_review_required"


@dataclass(frozen=True)
class DoclingTableQuality:
    table_id: str
    page_number: int
    row_count: int
    column_count: int
    non_empty_cell_ratio: float
    header_confidence: float
    numeric_column_count: int
    bbox_available: bool
    markdown_available: bool
    continuation_risk: bool
    score: float
    route: str


@dataclass(frozen=True)
class TableConsistencyResult:
    accepted_rows: list[dict[str, Any]]
    rejected_rows: list[dict[str, Any]]
    needs_review: bool
    warnings: tuple[str, ...]


def evaluate_docling_table_quality(
    table: ParsedTableText,
    *,
    continuation_risk: bool = False,
) -> DoclingTableQuality:
    rows = _table_rows(table)
    row_count = len(rows)
    column_count = max((len(row) for row in rows), default=0)
    non_empty = sum(1 for row in rows for cell in row if cell)
    total_cells = row_count * column_count
    non_empty_ratio = non_empty / total_cells if total_cells else 0.0
    header_confidence = _header_confidence(rows)
    numeric_column_count = _numeric_column_count(rows)
    markdown_available = bool((table.table_markdown or "").strip())
    bbox_available = table.bbox is not None
    score = _quality_score(
        row_count=row_count,
        column_count=column_count,
        non_empty_cell_ratio=non_empty_ratio,
        header_confidence=header_confidence,
        numeric_column_count=numeric_column_count,
        bbox_available=bbox_available,
        markdown_available=markdown_available,
        continuation_risk=continuation_risk,
    )
    partial = DoclingTableQuality(
        table_id=str(table.table_id),
        page_number=table.page_number,
        row_count=row_count,
        column_count=column_count,
        non_empty_cell_ratio=round(non_empty_ratio, 4),
        header_confidence=header_confidence,
        numeric_column_count=numeric_column_count,
        bbox_available=bbox_available,
        markdown_available=markdown_available,
        continuation_risk=continuation_risk,
        score=score,
        route="",
    )
    return DoclingTableQuality(
        **{
            **partial.__dict__,
            "route": select_table_extractor(partial),
        }
    )


def select_table_extractor(q: DoclingTableQuality) -> str:
    if (
        q.score >= 0.75
        and q.row_count >= 2
        and q.column_count >= 2
        and q.non_empty_cell_ratio >= 0.50
        and not q.continuation_risk
    ):
        return DOCLING_TABLE_LABELER_ROUTE

    if q.bbox_available and q.markdown_available:
        return GRANITE_REGION_CONTEXT_ROUTE

    return GRANITE_FULL_PAGE_REVIEW_ROUTE


def gate_docling_authoritative_rows(
    rows: list[dict[str, Any]],
    quality: DoclingTableQuality | None,
) -> TableConsistencyResult:
    if quality is None or quality.route != DOCLING_TABLE_LABELER_ROUTE:
        return TableConsistencyResult(
            accepted_rows=[dict(row) for row in rows],
            rejected_rows=[],
            needs_review=False,
            warnings=(),
        )

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    warnings: list[str] = []
    for row in rows:
        row_index = _optional_int(row.get("row_index"))
        if row_index is None:
            rejected.append(dict(row))
            warnings.append("candidate.missing_docling_row_index")
            continue
        accepted.append(
            {
                **row,
                "row_index": row_index,
                "table_id": row.get("table_id") or quality.table_id,
                "page_number": row.get("page_number") or quality.page_number,
            }
        )

    expected_data_rows = _expected_data_rows(quality)
    if expected_data_rows and _material_row_count_mismatch(
        extracted_count=len(accepted),
        expected_count=expected_data_rows,
    ):
        warnings.append("candidate.table_row_count_mismatch")

    unique_warnings = tuple(dict.fromkeys(warnings))
    return TableConsistencyResult(
        accepted_rows=accepted,
        rejected_rows=rejected,
        needs_review=bool(unique_warnings),
        warnings=unique_warnings,
    )


def apply_table_consistency_projection(
    normalized: dict[str, Any],
    metadata: dict[str, Any],
    consistency: TableConsistencyResult,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not consistency.rejected_rows and not consistency.warnings:
        return normalized, metadata

    table_consistency = {
        "acceptedRowCount": len(consistency.accepted_rows),
        "rejectedRowCount": len(consistency.rejected_rows),
        "needsReview": consistency.needs_review,
        "warnings": list(consistency.warnings),
    }
    metadata["tableConsistency"] = table_consistency
    metadata["repairs"] = [
        *metadata.get("repairs", []),
        "applied_docling_authoritative_table_row_gate",
    ]
    if consistency.rejected_rows:
        metadata["repairs"].append("rejected_docling_ungrounded_table_rows")

    normalized_metadata = dict(normalized.get("metadata") or {})
    normalized_metadata["tableConsistency"] = table_consistency
    normalized["metadata"] = normalized_metadata
    if consistency.needs_review:
        warnings = list(normalized.get("warnings") or [])
        warnings.extend(consistency.warnings)
        normalized["warnings"] = list(dict.fromkeys(warnings))
    return normalized, metadata


def _table_rows(table: ParsedTableText) -> list[list[str]]:
    json_rows = _rows_from_json(table.table_json)
    if json_rows:
        return json_rows
    return _rows_from_markdown(table.table_markdown)


def _rows_from_json(table_json: dict[str, Any]) -> list[list[str]]:
    data = table_json.get("data")
    data_grid = data.get("grid") if isinstance(data, dict) else None
    for candidate in (
        data_grid,
        table_json.get("grid"),
        table_json.get("rows"),
    ):
        if isinstance(candidate, list):
            rows = [_row_from_json(item) for item in candidate if isinstance(item, list)]
            return [row for row in rows if row]
    return []


def _row_from_json(row: list[Any]) -> list[str]:
    cells: list[str] = []
    for cell in row:
        if isinstance(cell, dict):
            value = cell.get("text")
            if value is None:
                value = cell.get("value")
            cells.append(_cell_text(value))
        else:
            cells.append(_cell_text(cell))
    return cells


def _rows_from_markdown(markdown: str | None) -> list[list[str]]:
    if not markdown:
        return []
    rows: list[list[str]] = []
    for line in markdown.splitlines():
        if "|" not in line:
            continue
        cells = [_cell_text(cell) for cell in line.strip().strip("|").split("|")]
        if not any(cells):
            continue
        if all(re.fullmatch(r":?-{2,}:?", cell or "") for cell in cells):
            continue
        rows.append(cells)
    return rows


def _cell_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _header_confidence(rows: list[list[str]]) -> float:
    if not rows:
        return 0.0
    header = rows[0]
    if not header or not any(header):
        return 0.0
    text_cells = sum(1 for cell in header if cell and not _looks_numeric(cell))
    if text_cells >= 2:
        return 0.9
    if text_cells == 1:
        return 0.6
    return 0.25


def _numeric_column_count(rows: list[list[str]]) -> int:
    if len(rows) < 2:
        return 0
    width = max(len(row) for row in rows)
    count = 0
    for column_index in range(width):
        values = [
            row[column_index]
            for row in rows[1:]
            if column_index < len(row) and row[column_index]
        ]
        if values and sum(1 for value in values if _looks_numeric(value)) / len(values) >= 0.5:
            count += 1
    return count


def _looks_numeric(value: str) -> bool:
    return bool(re.search(r"[$€£]?\s*\d+(?:[.,]\d+)?", value))


def _quality_score(
    *,
    row_count: int,
    column_count: int,
    non_empty_cell_ratio: float,
    header_confidence: float,
    numeric_column_count: int,
    bbox_available: bool,
    markdown_available: bool,
    continuation_risk: bool,
) -> float:
    score = (
        min(row_count / 4, 1.0) * 0.25
        + min(column_count / 4, 1.0) * 0.20
        + non_empty_cell_ratio * 0.25
        + header_confidence * 0.15
        + min(numeric_column_count / 2, 1.0) * 0.10
        + (0.03 if markdown_available else 0.0)
        + (0.02 if bbox_available else 0.0)
    )
    if continuation_risk:
        score -= 0.25
    return round(max(0.0, min(score, 1.0)), 4)


def _expected_data_rows(quality: DoclingTableQuality) -> int:
    if quality.header_confidence >= 0.5 and quality.row_count > 0:
        return quality.row_count - 1
    return quality.row_count


def _material_row_count_mismatch(*, extracted_count: int, expected_count: int) -> bool:
    if expected_count == 0:
        return extracted_count > 0
    difference = abs(extracted_count - expected_count)
    return difference >= 1 and difference / expected_count > 0.25


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
