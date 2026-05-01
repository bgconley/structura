from __future__ import annotations

import json

from lib.extraction.model_output_schemas import ModelOutputSchema
from lib.extraction.models import ExtractionSourceDocument
from lib.semantic_annotations.models import SemanticExtractionTask


def granite_prompt(
    *,
    source: ExtractionSourceDocument,
    schema_name: str,
    route_profile: str,
    semantic_task: SemanticExtractionTask | None,
    model_output_schema: ModelOutputSchema | None,
) -> str:
    base = (
        "Extract evidence-backed structured fields from the provided document page images. "
        f"Target schema: {schema_name}. Route profile: {route_profile}. "
        "Use Docling text only as context; image evidence is authoritative for visual fields. "
        "Return compact candidate JSON; do not transcribe long paragraphs or unrelated fields. "
    )
    if semantic_task is None:
        return (
            f"{base}Return JSON only in this shape: "
            '{"normalized":{...target schema JSON...},"confidence":{"overall":0.0,'
            '"schema_fit":0.0}}. Do not include Markdown fences or explanatory text.'
        )

    task_context = (
        "Semantic task from Qwen annotation: "
        f"type={semantic_task.semantic_type}; granite_task={semantic_task.granite_task}; "
        f"expected_fields={list(semantic_task.expected_fields)}; "
        f"grounding={semantic_task.grounding.kind}; reason={semantic_task.reason or ''}. "
    )
    docling_context = _docling_context(source, semantic_task)
    if model_output_schema is None:
        return (
            f"{base}{task_context}"
            "For grounded semantic tasks, extract only the visible fields needed for that task; "
            "omit uncertain values instead of adding prose. "
            "Return JSON only. Do not include Markdown fences or explanatory text."
            f"{docling_context}"
        )

    schema_text = json.dumps(model_output_schema.schema, indent=2, sort_keys=True)
    if _is_table_region(semantic_task):
        return (
            "<tables_json>\n"
            f"{base}"
            f"{task_context}"
            "Extract only the line/service rows visible in the grounded table or region. "
            "For line-item contracts, populate line_items with row objects; do not return "
            "standalone quantity or amount arrays instead of rows. "
            "If visible rows are not present, return an empty line_items array instead of prose. "
            "Do not infer line items from totals, disclaimers, or payment text. "
            "Use the JSON Schema below as the output contract. "
            "Return null for fields you cannot find. "
            "Return ONLY valid JSON matching the schema instance, not the schema itself. "
            f"JSON Schema:\n{schema_text}"
            f"{docling_context}"
        )
    return (
        f"{base}{task_context}"
        "Extract only the requested observation fields. "
        "Do not transcribe paragraphs or unrelated receipt/legal/payment text. "
        "Return null or an empty list when evidence is not visible. "
        "Prefer fewer grounded values over broad summaries.\n"
        "Return a JSON object matching this schema:\n\n"
        f"{schema_text}\n\n"
        "Return null for fields you cannot find.\n"
        "Return ONLY valid JSON.\n"
        "Return an instance of the JSON with extracted values, not the schema itself."
        f"{docling_context}"
    )


def _docling_context(
    source: ExtractionSourceDocument,
    task: SemanticExtractionTask,
) -> str:
    table_context = _table_context(source, task)
    page_context = _page_context(source, task)
    context_parts = [part for part in (table_context, page_context) if part]
    if not context_parts:
        return ""
    return "\n\nDocling grounded context:\n" + "\n".join(context_parts)


def _table_context(source: ExtractionSourceDocument, task: SemanticExtractionTask) -> str:
    tables = []
    if task.grounding.table_id:
        tables = [table for table in source.tables if table.table_id == task.grounding.table_id]
    elif task.grounding.page_id:
        page = next(
            (page for page in source.pages if page.page_id == task.grounding.page_id),
            None,
        )
        if page is not None:
            tables = [table for table in source.tables if table.page_number == page.page_number]
    if not tables:
        return ""
    rendered: list[str] = []
    for table in tables[:2]:
        if table.table_markdown:
            rendered.append(
                f"Table page={table.page_number} index={table.table_index}:\n"
                f"{table.table_markdown[:1600]}"
            )
        elif table.table_json:
            table_text = _render_table_json(table.table_json)
            rendered.append(
                f"Table page={table.page_number} index={table.table_index} rows:\n"
                f"{table_text[:2400]}"
            )
    return "\n".join(rendered)


def _render_table_json(table_json: dict[str, object]) -> str:
    grid = _table_grid(table_json)
    if grid:
        lines = []
        for row in grid[:80]:
            cells = [_cell_text(cell) for cell in row]
            text_cells = [cell for cell in cells if cell]
            if text_cells:
                lines.append(" | ".join(text_cells))
        if lines:
            return "\n".join(lines)
    return json.dumps(table_json, sort_keys=True)


def _table_grid(table_json: dict[str, object]) -> list[list[object]]:
    data = table_json.get("data")
    if isinstance(data, dict):
        grid = data.get("grid")
        if isinstance(grid, list):
            return [row for row in grid if isinstance(row, list)]
    grid = table_json.get("grid")
    if isinstance(grid, list):
        return [row for row in grid if isinstance(row, list)]
    rows = table_json.get("rows")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, list)]
    return []


def _cell_text(cell: object) -> str:
    if isinstance(cell, dict):
        text = cell.get("text")
        if text is None:
            text = cell.get("value")
        return " ".join(str(text or "").split())
    return " ".join(str(cell).split())


def _page_context(source: ExtractionSourceDocument, task: SemanticExtractionTask) -> str:
    page = None
    if task.grounding.page_id:
        page = next(
            (
                candidate
                for candidate in source.pages
                if candidate.page_id == task.grounding.page_id
            ),
            None,
        )
    if page is None and task.grounding.table_id:
        table = next(
            (
                candidate
                for candidate in source.tables
                if candidate.table_id == task.grounding.table_id
            ),
            None,
        )
        if table is not None:
            page = next(
                (
                    candidate
                    for candidate in source.pages
                    if candidate.page_number == table.page_number
                ),
                None,
            )
    if page is None or not page.text:
        return ""
    return f"Page {page.page_number} text excerpt:\n{page.text[:1600]}"


def _is_table_region(task: SemanticExtractionTask) -> bool:
    return task.granite_task in {
        "tables_json",
        "tables_html",
        "tables_otsl",
    } or task.semantic_type in {
        "invoice_line_item_table",
        "covered_services_line_item_table",
        "receipt_line_item_table",
        "retail_order_line_item_table",
        "service_record_line_item_table",
        "dispute_transaction_table",
    }
