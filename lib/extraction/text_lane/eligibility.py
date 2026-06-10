"""Text-lane eligibility: which regions may extract from Docling text.

The text lane requires a trustworthy text layer at the grounded location;
everything else stays on the vision path (ADR 0006 X2). Eligibility combines
the page-quality signals from lib/documents/quality.py with the Docling
table-signal audit, and always returns a reason for lane telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lib.extraction.models import ExtractionSourceDocument, ParsedPageText, ParsedTableText
from lib.extraction.text_lane.table_grid import TableGrid
from lib.semantic_annotations.docling_audit import build_docling_audit
from lib.semantic_annotations.models import SemanticExtractionTask
from lib.semantic_annotations.task_routing import LINE_ITEM_TABLE_SEMANTIC_TYPES

Lane = Literal["text", "vision"]

# Quality reasons that disqualify a page from verbatim text extraction.
# complex_layout deliberately stays eligible: multi-table pages are exactly
# where the cell grid is most valuable.
_DIFFICULT_PAGE_REASONS = frozenset(
    {
        "handwriting",
        "missing_text_layer",
        "low_text_density",
        "low_ocr_confidence",
        "degraded_scan",
    }
)


@dataclass(frozen=True)
class LaneDecision:
    lane: Lane
    reason: str
    page_number: int | None = None
    table_id: str | None = None


def text_lane_eligibility(
    source: ExtractionSourceDocument,
    *,
    semantic_task: SemanticExtractionTask | None,
) -> LaneDecision:
    if semantic_task is None:
        return LaneDecision(lane="vision", reason="no_semantic_task")
    if semantic_task.semantic_type not in LINE_ITEM_TABLE_SEMANTIC_TYPES:
        return LaneDecision(lane="vision", reason="region_not_line_item_table")
    table = _grounded_table(source, semantic_task)
    if table is None:
        return LaneDecision(lane="vision", reason="no_grounded_docling_table")
    grid = TableGrid.from_parsed_table(table)
    if grid is None:
        return LaneDecision(
            lane="vision",
            reason="table_grid_missing",
            page_number=table.page_number,
            table_id=str(table.table_id),
        )
    if not grid.data_row_indexes:
        return LaneDecision(
            lane="vision",
            reason="table_grid_has_no_data_rows",
            page_number=table.page_number,
            table_id=str(table.table_id),
        )
    table_signal = _table_signal(source, table)
    if table_signal != "strong":
        return LaneDecision(
            lane="vision",
            reason=f"table_signal_{table_signal or 'unknown'}",
            page_number=table.page_number,
            table_id=str(table.table_id),
        )
    difficult = _difficult_page_reasons(source, table.page_number)
    if difficult:
        return LaneDecision(
            lane="vision",
            reason="difficult_page:" + ",".join(difficult),
            page_number=table.page_number,
            table_id=str(table.table_id),
        )
    return LaneDecision(
        lane="text",
        reason="strong_table_on_text_page",
        page_number=table.page_number,
        table_id=str(table.table_id),
    )


def _grounded_table(
    source: ExtractionSourceDocument,
    semantic_task: SemanticExtractionTask,
) -> ParsedTableText | None:
    grounding = semantic_task.grounding
    if grounding.table_id is not None:
        for table in source.tables:
            if table.table_id == grounding.table_id:
                return table
    if grounding.element_id is not None:
        for table in source.tables:
            if table.element_id == grounding.element_id:
                return table
    return None


def _table_signal(source: ExtractionSourceDocument, table: ParsedTableText) -> str | None:
    audit = build_docling_audit(source)
    for summary in audit.table_summaries:
        if summary.table_id == table.table_id:
            return summary.table_signal
    return None


def _difficult_page_reasons(
    source: ExtractionSourceDocument,
    page_number: int,
) -> tuple[str, ...]:
    # Imported lazily: lib.documents.quality imports lib.review at module
    # scope, which initializes lib.extraction and would close an import
    # cycle back into this module when quality loads first (API startup).
    from lib.documents.quality import PageQualityInput, classify_page_quality

    page = _page(source, page_number)
    if page is None:
        return ("page_not_found",)
    signals = classify_page_quality(
        PageQualityInput(
            page_number=page.page_number,
            text=page.text,
            has_text_layer=page.has_text_layer,
            ocr_confidence=page.ocr_confidence,
            metadata=page.metadata,
            table_count=sum(1 for item in source.tables if item.page_number == page_number),
            figure_count=0,
        )
    )
    return tuple(reason for reason in signals.reasons if reason in _DIFFICULT_PAGE_REASONS)


def _page(source: ExtractionSourceDocument, page_number: int) -> ParsedPageText | None:
    for page in source.pages:
        if page.page_number == page_number:
            return page
    return None
