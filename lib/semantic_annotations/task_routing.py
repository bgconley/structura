from __future__ import annotations

from typing import Any

LINE_ITEM_TABLE_SEMANTIC_TYPES = frozenset(
    {
        "covered_services_line_item_table",
        "invoice_line_item_table",
        "receipt_line_item_table",
        "retail_order_line_item_table",
        "service_record_line_item_table",
    }
)
TABLE_GRANITE_TASKS = frozenset({"tables_json", "tables_html", "tables_otsl"})


def corrected_granite_task_for_semantic_type(
    *,
    semantic_type: str,
    granite_task: str | None,
) -> tuple[str | None, dict[str, Any] | None]:
    if granite_task in {None, "ignore"}:
        return granite_task, None
    if semantic_type not in LINE_ITEM_TABLE_SEMANTIC_TYPES:
        return granite_task, None
    if granite_task in TABLE_GRANITE_TASKS:
        return granite_task, None
    return (
        "tables_json",
        {
            "original_granite_task": granite_task,
            "repaired_granite_task": "tables_json",
            "reason": "line_item_semantic_type_requires_table_task",
        },
    )
