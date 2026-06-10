"""Text-lane eligibility: which regions may extract from Docling text.

The text lane requires a trustworthy text layer at the grounded location;
everything else stays on the vision path (ADR 0006 X2). Eligibility combines
the page-quality signals from lib/documents/quality.py with structural
checks on the parsed cell grid, and always returns a reason for lane
telemetry.

The docling_audit table signal is deliberately not consulted: it counts
table_markdown rows plus a table_json["rows"] key that the Docling shape
does not have, and live document_tables rows persist empty markdown, so it
reports every real grid as weak. The grid itself (parseable cells, data
rows, >=2 columns) is the structural signal here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lib.extraction.models import ExtractionSourceDocument, ParsedPageText, ParsedTableText
from lib.extraction.text_lane.table_grid import TableGrid
from lib.semantic_annotations.models import SemanticExtractionTask
from lib.semantic_annotations.task_routing import (
    KVP_SEMANTIC_TYPES,
    LINE_ITEM_TABLE_SEMANTIC_TYPES,
)

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
    if grid.num_cols < 2:
        return LaneDecision(
            lane="vision",
            reason="table_grid_too_narrow",
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
        reason="usable_grid_on_text_page",
        page_number=table.page_number,
        table_id=str(table.table_id),
    )


def text_lane_kvp_eligibility(
    source: ExtractionSourceDocument,
    *,
    semantic_task: SemanticExtractionTask | None,
) -> LaneDecision:
    """KVP-lane eligibility: a grounded, readable page with parsed elements.

    KVP regions are typically page-grounded (no Docling table), so the
    screens are the page-quality reasons plus the presence of element text
    to build span candidates from.
    """
    if semantic_task is None:
        return LaneDecision(lane="vision", reason="no_semantic_task")
    if semantic_task.semantic_type not in KVP_SEMANTIC_TYPES:
        return LaneDecision(lane="vision", reason="region_not_kvp")
    page_number = grounded_page_number(source, semantic_task)
    if page_number is None:
        return LaneDecision(lane="vision", reason="no_grounded_page")
    if not any(
        element.page_number == page_number and element.text.strip() for element in source.elements
    ):
        return LaneDecision(
            lane="vision",
            reason="no_page_elements",
            page_number=page_number,
        )
    difficult = _difficult_page_reasons(source, page_number)
    if difficult:
        return LaneDecision(
            lane="vision",
            reason="difficult_page:" + ",".join(difficult),
            page_number=page_number,
        )
    return LaneDecision(
        lane="text",
        reason="kvp_spans_on_text_page",
        page_number=page_number,
    )


def grounded_page_number(
    source: ExtractionSourceDocument,
    semantic_task: SemanticExtractionTask,
) -> int | None:
    grounding = semantic_task.grounding
    if grounding.page_id is not None:
        for page in source.pages:
            if page.page_id == grounding.page_id:
                return page.page_number
    if grounding.element_id is not None:
        for element in source.elements:
            if element.element_id == grounding.element_id:
                return element.page_number
    if grounding.table_id is not None:
        for table in source.tables:
            if table.table_id == grounding.table_id:
                return table.page_number
    return None


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
