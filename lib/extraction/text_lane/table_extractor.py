"""Deterministic line-item extraction from the Docling cell grid (ADR 0006).

Given a TableGrid and model column roles, every value is copied verbatim from
its cell and parsed with the shared deterministic parsers; the anchor is the
cell's own table row (page, table_id, row_index, row bbox), so it is exact by
construction. Totals rows (subtotal/tax/total keywords in the description
column) emit the family's totals facts instead of line items. The output is
the standard RegionExtractionEnvelope so claims, candidates, reconciliation,
and review consume the text lane unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from lib.extraction.model_output_value_parsing import parse_decimal_text
from lib.extraction.models import ExtractionSourceDocument
from lib.extraction.region_envelope import (
    EvidenceRef,
    RegionExtractionEnvelope,
    RegionFact,
    RegionLineItem,
)
from lib.extraction.text_lane.column_labeling import IGNORE_ROLE, ColumnLabeling
from lib.extraction.text_lane.table_grid import TableGrid, TableGridCell
from lib.semantic_annotations.models import SemanticExtractionTask

TEXT_LANE_TABLE_METHOD = "text_lane_table.v1"

MONEY_ROLES = frozenset(
    {
        "unit_price",
        "gross_amount",
        "allowed_amount",
        "plan_paid",
        "discount",
        "tax_amount",
        "amount",
    }
)
_TEXT_ROLES = frozenset(
    {"description", "code", "unit", "service_date", "tax_category_hint", "category_hint"}
)
_ROLE_TO_LINE_ITEM_FIELD = {
    "description": "description",
    "code": "code",
    "quantity": "quantity",
    "unit": "unit",
    "unit_price": "unit_price",
    "gross_amount": "gross_amount",
    "allowed_amount": "allowed_amount",
    "plan_paid": "plan_paid_amount",
    "discount": "discount_amount",
    "tax_amount": "tax_amount",
    "amount": "net_amount",
    "service_date": "service_date",
    "tax_category_hint": "tax_category_hint",
    "category_hint": "category_hint",
}
_MAX_TOTALS_LABEL_WORDS = 5
_MAX_ROW_SOURCE_TEXT_CHARS = 400
# Roles whose populated values mark a row as a line item even when its
# description carries a totals word ("Total Cereal | 1 | 5.99"). quantity
# only: totals rows can legitimately carry a value in the unit-price column
# (a tax RATE next to the tax amount), so unit_price must not veto totals.
_LINE_ITEM_SHAPE_ROLES = frozenset({"quantity"})
# Totals-looking labels with no mapped family key are suppressed rather than
# line-itemized, so an EOB "Totals" row cannot double-count service lines.
_TOTALS_SUPPRESS_PHRASES = (
    "grand total",
    "amount due",
    "balance due",
    "sub-total",
    "sub total",
    "subtotal",
    "totals",
    "total",
    "balance",
)

# Ordered phrase -> canonical totals key per claim family; first match wins,
# so more specific phrases must precede the bare "total".
_TOTALS_PHRASE_KEYS: dict[str, tuple[tuple[str, str], ...]] = {
    "invoice": (
        ("subtotal", "invoice.subtotal"),
        ("sub-total", "invoice.subtotal"),
        ("sub total", "invoice.subtotal"),
        ("sales tax", "invoice.tax_total"),
        ("tax", "invoice.tax_total"),
        ("shipping", "invoice.shipping_total"),
        ("freight", "invoice.shipping_total"),
        ("discount", "invoice.discount_total"),
        ("amount paid", "invoice.amount_paid"),
        ("payment received", "invoice.amount_paid"),
        ("balance due", "invoice.balance_due"),
        ("amount due", "invoice.balance_due"),
        ("balance", "invoice.balance_due"),
        ("total", "invoice.total_amount"),
    ),
    "receipt": (
        ("subtotal", "receipt.transaction.subtotal"),
        ("sub-total", "receipt.transaction.subtotal"),
        ("sub total", "receipt.transaction.subtotal"),
        ("sales tax", "receipt.transaction.tax"),
        ("tax", "receipt.transaction.tax"),
        ("tip", "receipt.transaction.tip"),
        ("gratuity", "receipt.transaction.tip"),
        ("discount", "receipt.transaction.discount_total"),
        ("total", "receipt.transaction.total"),
    ),
    "service_record": (
        ("subtotal", "service_record.subtotal"),
        ("sub-total", "service_record.subtotal"),
        ("sub total", "service_record.subtotal"),
        ("sales tax", "service_record.tax"),
        ("tax", "service_record.tax"),
        ("total", "service_record.total"),
    ),
    "retail_order": (("total", "retail_order.total"),),
    "medical_eob": (
        ("total billed", "medical_eob.total_billed"),
        ("total allowed", "medical_eob.total_allowed"),
        ("total plan paid", "medical_eob.total_plan_paid"),
        ("plan paid", "medical_eob.total_plan_paid"),
        ("patient responsibility", "medical_eob.total_patient_responsibility"),
    ),
}


@dataclass(frozen=True)
class TableLaneExtraction:
    envelope: RegionExtractionEnvelope
    line_item_count: int
    totals_fact_count: int
    skipped_row_count: int
    suppressed_totals_row_count: int = 0


@dataclass(frozen=True)
class _TotalsRowOutcome:
    fact: RegionFact | None = None
    suppress_reason: str | None = None


def extract_table_region(
    *,
    source: ExtractionSourceDocument,
    semantic_task: SemanticExtractionTask,
    grid: TableGrid,
    labeling: ColumnLabeling,
    family: str,
    target_schema: str,
) -> TableLaneExtraction:
    roles = {
        index: role
        for index, role in labeling.roles.items()
        if role != IGNORE_ROLE and role in _ROLE_TO_LINE_ITEM_FIELD
    }
    description_columns = [index for index, role in sorted(roles.items()) if role == "description"]
    money_columns = [index for index, role in sorted(roles.items()) if role in MONEY_ROLES]
    page_id = _page_id(source, grid.page_number)
    line_items: list[RegionLineItem] = []
    facts: list[RegionFact] = []
    warnings: list[str] = []
    skipped = 0
    suppressed = 0
    for row_index in grid.data_row_indexes:
        cells = grid.row_cells(row_index)
        evidence = _row_evidence(
            source=source,
            semantic_task=semantic_task,
            grid=grid,
            row_index=row_index,
            cells=cells,
            page_id=page_id,
        )
        totals_outcome = _classify_totals_row(
            family=family,
            cells=cells,
            roles=roles,
            description_columns=description_columns,
            money_columns=money_columns,
            evidence=evidence,
            row_index=row_index,
        )
        if totals_outcome is not None:
            if totals_outcome.fact is not None:
                facts.append(totals_outcome.fact)
            else:
                suppressed += 1
            continue
        item = _line_item(
            roles=roles,
            cells=cells,
            evidence=evidence,
            grid=grid,
            row_index=row_index,
        )
        if item is None:
            skipped += 1
            continue
        line_items.append(item)
    if not line_items and not facts:
        warnings.append("text_lane_table_produced_no_rows")
    envelope = RegionExtractionEnvelope(
        document_id=str(source.document_id),
        semantic_annotation_id=str(semantic_task.annotation_id),
        semantic_region_id=str(semantic_task.region_id),
        resolved_document_type=family,
        semantic_type=semantic_task.semantic_type,
        target_schema=target_schema,
        model_output_schema_name=TEXT_LANE_TABLE_METHOD,
        coverage={
            "lane": "text",
            "table_id": grid.table_id,
            "page_number": grid.page_number,
            "header_fingerprint": grid.header_fingerprint(),
            "header_labels": list(grid.header_labels()),
            "column_roles": labeling.roles_json(),
            "data_row_count": len(grid.data_row_indexes),
            "line_item_count": len(line_items),
            "totals_fact_count": len(facts),
            "skipped_row_count": skipped,
            "suppressed_totals_row_count": suppressed,
            "labeling": {
                "model_name": labeling.model_name,
                "model_version": labeling.model_version,
                "prompt_version": labeling.prompt_version,
                "from_cache": labeling.from_cache,
            },
        },
        facts=facts,
        line_items=line_items,
        warnings=warnings,
    )
    return TableLaneExtraction(
        envelope=envelope,
        line_item_count=len(line_items),
        totals_fact_count=len(facts),
        skipped_row_count=skipped,
        suppressed_totals_row_count=suppressed,
    )


def _line_item(
    *,
    roles: dict[int, str],
    cells: tuple[TableGridCell | None, ...],
    evidence: list[EvidenceRef],
    grid: TableGrid,
    row_index: int,
) -> RegionLineItem | None:
    values: dict[str, Any] = {}
    for column_index, role in sorted(roles.items()):
        cell = cells[column_index] if column_index < len(cells) else None
        if cell is None:
            continue
        text = cell.normalized_text
        if not text:
            continue
        parsed = _parsed_role_value(role, text)
        if parsed is None:
            continue
        field_name = _ROLE_TO_LINE_ITEM_FIELD[role]
        if field_name in values:
            continue
        values[field_name] = parsed
    if not values:
        return None
    return RegionLineItem(
        ordinal=row_index,
        description=values.get("description"),
        code=values.get("code"),
        quantity=values.get("quantity"),
        unit=values.get("unit"),
        unit_price=values.get("unit_price"),
        gross_amount=values.get("gross_amount"),
        allowed_amount=values.get("allowed_amount"),
        plan_paid_amount=values.get("plan_paid_amount"),
        net_amount=values.get("net_amount"),
        discount_amount=values.get("discount_amount"),
        tax_amount=values.get("tax_amount"),
        service_date=values.get("service_date"),
        tax_category_hint=values.get("tax_category_hint"),
        category_hint=values.get("category_hint"),
        evidence=evidence,
        row_index=row_index,
        table_id=grid.table_id,
        page_number=grid.page_number,
    )


def _parsed_role_value(role: str, text: str) -> Any | None:
    if role in MONEY_ROLES or role == "quantity":
        return parse_decimal_text(text)
    if role in _TEXT_ROLES:
        return text
    return None


def _classify_totals_row(
    *,
    family: str,
    cells: tuple[TableGridCell | None, ...],
    roles: dict[int, str],
    description_columns: list[int],
    money_columns: list[int],
    evidence: list[EvidenceRef],
    row_index: int,
) -> _TotalsRowOutcome | None:
    """Decide whether a data row is a totals row.

    Returns None for ordinary line-item rows. Totals labels match on word
    boundaries only ("Taxi" is not "tax"), and a row carrying quantity or
    unit-price values is always a line item even when its description
    contains a totals word ("Total Cereal | 1 | 5.99"). Totals-looking rows
    with no mapped family key (e.g. an EOB "Totals" band) are suppressed so
    they cannot double-count as line items.
    """
    label_columns = description_columns or [0]
    label = ""
    for column_index in label_columns:
        cell = cells[column_index] if column_index < len(cells) else None
        if cell is not None and cell.normalized_text:
            label = cell.normalized_text
            break
    if not label or len(label.split()) > _MAX_TOTALS_LABEL_WORDS:
        return None
    if _row_has_line_item_shape(cells, roles):
        return None
    lowered = label.casefold()
    phrase_keys = _TOTALS_PHRASE_KEYS.get(family, ())
    canonical_key = next(
        (key for phrase, key in phrase_keys if _phrase_matches(phrase, lowered)),
        None,
    )
    if canonical_key is not None:
        amount_cell = _totals_amount_cell(cells, roles=roles, money_columns=money_columns)
        amount = (
            parse_decimal_text(amount_cell.normalized_text) if amount_cell is not None else None
        )
        if amount_cell is None or amount is None:
            return _TotalsRowOutcome(suppress_reason="totals_row_without_amount")
        return _TotalsRowOutcome(
            fact=RegionFact(
                name=canonical_key,
                value={"amount": amount},
                value_type="money",
                evidence=evidence,
                source_text=amount_cell.normalized_text,
                source_payload={
                    "row_index": row_index,
                    "label": label,
                    "method": TEXT_LANE_TABLE_METHOD,
                },
            )
        )
    if any(_phrase_matches(phrase, lowered) for phrase in _TOTALS_SUPPRESS_PHRASES):
        return _TotalsRowOutcome(suppress_reason="unmapped_totals_row")
    return None


def _phrase_matches(phrase: str, lowered_label: str) -> bool:
    # Hyphens count as word characters at the phrase edges so "Tip-top" does
    # not match "tip"; hyphens inside a phrase ("sub-total") still match.
    pattern = rf"(?<![a-z0-9-]){re.escape(phrase)}(?![a-z0-9-])"
    return re.search(pattern, lowered_label) is not None


def _row_has_line_item_shape(
    cells: tuple[TableGridCell | None, ...],
    roles: dict[int, str],
) -> bool:
    for column_index, role in roles.items():
        if role not in _LINE_ITEM_SHAPE_ROLES:
            continue
        cell = cells[column_index] if column_index < len(cells) else None
        if cell is None or not cell.normalized_text:
            continue
        if parse_decimal_text(cell.normalized_text) is not None:
            return True
    return False


def _totals_amount_cell(
    cells: tuple[TableGridCell | None, ...],
    *,
    roles: dict[int, str],
    money_columns: list[int],
) -> TableGridCell | None:
    """Pick the totals value cell: the amount-role column first, then the
    remaining money-role columns right-to-left, then the rightmost parseable
    cell. Left-to-right order would capture rates/unit prices instead of the
    extended amount."""
    amount_columns = [index for index in money_columns if roles.get(index) == "amount"]
    other_money_columns = [
        index for index in sorted(money_columns, reverse=True) if roles.get(index) != "amount"
    ]
    for column_index in (*amount_columns, *other_money_columns):
        cell = cells[column_index] if column_index < len(cells) else None
        if cell is not None and parse_decimal_text(cell.normalized_text) is not None:
            return cell
    for cell in reversed(cells):
        if cell is not None and cell.normalized_text:
            if parse_decimal_text(cell.normalized_text) is not None:
                return cell
    return None


def _row_evidence(
    *,
    source: ExtractionSourceDocument,
    semantic_task: SemanticExtractionTask,
    grid: TableGrid,
    row_index: int,
    cells: tuple[TableGridCell | None, ...],
    page_id: str | None,
) -> list[EvidenceRef]:
    row_cells = [cell for cell in cells if cell is not None]
    source_text = " | ".join(cell.normalized_text for cell in row_cells if cell.normalized_text)[
        :_MAX_ROW_SOURCE_TEXT_CHARS
    ]
    return [
        EvidenceRef(
            document_id=str(source.document_id),
            semantic_annotation_id=str(semantic_task.annotation_id),
            semantic_region_id=str(semantic_task.region_id),
            page_number=grid.page_number,
            page_id=page_id,
            element_id=grid.element_id,
            table_id=grid.table_id,
            row_index=row_index,
            bbox=_row_bbox(row_cells),
            source_text=source_text or None,
            source_engine="docling",
        )
    ]


def _row_bbox(cells: list[TableGridCell]) -> list[float] | None:
    boxes = [cell.bbox for cell in cells if cell.bbox is not None]
    if not boxes:
        return None
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def _page_id(source: ExtractionSourceDocument, page_number: int) -> str | None:
    for page in source.pages:
        if page.page_number == page_number:
            return str(page.page_id)
    return None
