from __future__ import annotations

from uuid import uuid4

from lib.extraction.docling_table_quality import (
    DoclingTableQuality,
    evaluate_docling_table_quality,
    gate_docling_authoritative_rows,
    select_table_extractor,
)
from lib.extraction.models import ParsedTableText


def test_strong_table_routes_to_docling_table_plus_granite_labeler() -> None:
    table = ParsedTableText(
        table_id=uuid4(),
        page_number=2,
        table_index=1,
        table_markdown=(
            "| Description | Qty | Amount |\n"
            "| --- | ---: | ---: |\n"
            "| Alignment service | 1 | $99.00 |\n"
            "| Tire rotation | 1 | $45.00 |"
        ),
        table_json={
            "data": {
                "grid": [
                    [{"text": "Description"}, {"text": "Qty"}, {"text": "Amount"}],
                    [{"text": "Alignment service"}, {"text": "1"}, {"text": "$99.00"}],
                    [{"text": "Tire rotation"}, {"text": "1"}, {"text": "$45.00"}],
                ]
            }
        },
        bbox=[10, 20, 500, 220],
    )

    quality = evaluate_docling_table_quality(table)

    assert quality.table_id == str(table.table_id)
    assert quality.page_number == 2
    assert quality.row_count == 3
    assert quality.column_count == 3
    assert quality.numeric_column_count >= 2
    assert quality.route == "docling_table_plus_granite_labeler"
    assert select_table_extractor(quality) == "docling_table_plus_granite_labeler"


def test_weak_table_routes_conservatively_to_region_context() -> None:
    quality = DoclingTableQuality(
        table_id=str(uuid4()),
        page_number=1,
        row_count=1,
        column_count=2,
        non_empty_cell_ratio=1.0,
        header_confidence=0.25,
        numeric_column_count=0,
        bbox_available=True,
        markdown_available=True,
        continuation_risk=False,
        score=0.42,
        route="",
    )

    assert select_table_extractor(quality) == "granite_region_with_docling_context"


def test_continuation_risk_routes_conservatively() -> None:
    quality = DoclingTableQuality(
        table_id=str(uuid4()),
        page_number=3,
        row_count=4,
        column_count=3,
        non_empty_cell_ratio=0.95,
        header_confidence=0.85,
        numeric_column_count=2,
        bbox_available=True,
        markdown_available=True,
        continuation_risk=True,
        score=0.91,
        route="",
    )

    assert select_table_extractor(quality) == "granite_region_with_docling_context"


def test_authoritative_table_gate_rejects_rows_without_docling_row_index() -> None:
    quality = DoclingTableQuality(
        table_id=str(uuid4()),
        page_number=1,
        row_count=3,
        column_count=3,
        non_empty_cell_ratio=1.0,
        header_confidence=0.85,
        numeric_column_count=2,
        bbox_available=True,
        markdown_available=True,
        continuation_risk=False,
        score=0.89,
        route="docling_table_plus_granite_labeler",
    )

    result = gate_docling_authoritative_rows(
        [
            {"description": "Grounded service", "row_index": 1, "amount": "$99.00"},
            {"description": "Invented service", "amount": "$12.00"},
        ],
        quality,
    )

    assert [row["description"] for row in result.accepted_rows] == ["Grounded service"]
    assert [row["description"] for row in result.rejected_rows] == ["Invented service"]
    assert "candidate.missing_docling_row_index" in result.warnings


def test_row_count_mismatch_records_review_required_taxonomy_code() -> None:
    quality = DoclingTableQuality(
        table_id=str(uuid4()),
        page_number=1,
        row_count=4,
        column_count=3,
        non_empty_cell_ratio=1.0,
        header_confidence=0.9,
        numeric_column_count=2,
        bbox_available=True,
        markdown_available=True,
        continuation_risk=False,
        score=0.92,
        route="docling_table_plus_granite_labeler",
    )

    result = gate_docling_authoritative_rows(
        [{"description": "Only one extracted row", "row_index": 1, "amount": "$99.00"}],
        quality,
    )

    assert result.needs_review is True
    assert "candidate.table_row_count_mismatch" in result.warnings
