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

    if _is_line_item_region(semantic_task):
        return (
            "<tables_json>\n"
            f"{base}"
            f"{task_context}"
            "Extract line items as compact row candidates from the grounded region. "
            "Use Docling table rows when provided. "
            "When Docling rows are labeled with row_index, include that row_index for "
            "each extracted row and omit rows that cannot be matched to a Docling row. "
            "Return at most 20 row objects for this grounded region. "
            "Do not output table dimensions, table cells, or table schema. "
            "Do not copy these instructions into any field. "
            "Do not include source_text; Structura records evidence separately. "
            "Do not include page summaries, row grids, coordinate dumps, or explanatory text. "
            "Keep confidence as an empty object or concise numeric scores only. "
            "If visible rows are not present, return an empty list instead of prose. "
            f"{_line_item_shape(model_output_schema)} "
            "Return ONLY a valid JSON object matching the response schema supplied by the API."
            f"{docling_context}"
        )

    if _is_table_region(semantic_task):
        return (
            "<tables_json>\n"
            f"{base}"
            f"{task_context}"
            "Extract only values visible in the grounded table or page region. "
            "Use Docling table rows as supplemental context, but do not output grid metadata, "
            "cell coordinates, schema keys, prompt text, or explanatory prose. "
            "Do not infer line items from totals, disclaimers, or payment text. "
            "Return null for fields you cannot find. "
            f"{_compact_shape_for_schema(model_output_schema.name)} "
            "Return ONLY a valid JSON object matching the response schema supplied by the API."
            f"{docling_context}"
        )
    return (
        f"{base}{task_context}"
        "Extract only the requested observation fields that are directly visible. "
        "Do not transcribe paragraphs or unrelated receipt/legal/payment text. "
        "Do not output schema_name, schema_version, properties, required, metadata, "
        "prompt text, or instructions unless those are literally visible document fields. "
        "Return null or an empty list when evidence is not visible. "
        "Prefer fewer grounded values over broad summaries. "
        "When expected_fields conflict with the supplied API response schema, the API "
        "response schema wins. Keep confidence as an empty object and do not place "
        "extracted facts inside confidence. "
        f"{_compact_shape_for_schema(model_output_schema.name)} "
        "Return ONLY a valid JSON object matching the response schema supplied by the API."
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
            table_text = _render_table_markdown(table.table_markdown)
            rendered.append(
                f"Table page={table.page_number} index={table.table_index}:\n{table_text[:1600]}"
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
        for index, row in enumerate(grid[:80]):
            cells = [_cell_text(cell) for cell in row]
            text_cells = [cell for cell in cells if cell]
            if text_cells:
                lines.append(f"row_index={index}: " + " | ".join(text_cells))
        if lines:
            return "\n".join(lines)
    return json.dumps(table_json, sort_keys=True)


def _render_table_markdown(table_markdown: str) -> str:
    lines: list[str] = []
    for index, line in enumerate(table_markdown.splitlines()):
        if "|" not in line:
            continue
        text = " ".join(line.strip().split())
        if text:
            lines.append(f"row_index={index}: {text}")
    return "\n".join(lines) or table_markdown


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
    } and not _is_line_item_region(task)


def _is_line_item_region(task: SemanticExtractionTask) -> bool:
    return task.semantic_type in {
        "invoice_line_item_table",
        "covered_services_line_item_table",
        "receipt_line_item_table",
        "retail_order_line_item_table",
        "service_record_line_item_table",
    }


def _line_item_shape(model_output_schema: ModelOutputSchema) -> str:
    if model_output_schema.name == "granite_medical_service_lines.v1":
        return (
            'Use shape {"service_lines":[{"ordinal":1,'
            '"service_description":"visible service","service_date":null,'
            '"procedure_code":null,"billed_amount":null,"allowed_amount":null,'
            '"paid_amount":null,"patient_responsibility":null}],"confidence":{}}.'
        )
    return (
        'Use shape {"line_items":[{"ordinal":1,"description":"visible row",'
        '"quantity":null,"unit_price":null,"amount":null}],'
        '"totals":{"subtotal":null,"tax_total":null,'
        '"shipping_total":null,"discount_total":null,"total":null},'
        '"confidence":{}}.'
    )


def _compact_shape_for_schema(schema_name: str) -> str:
    if schema_name == "granite_generic_kvp.v1":
        return (
            'Use shape {"fields":[{"name":"visible_field","value":"visible value",'
            '"confidence":0.0,"source_text":"short visible text"}],"confidence":{}}.'
        )
    if schema_name == "granite_dispute_form.v1":
        return (
            'Use shape {"account_holder":null,"merchant_name":null,'
            '"transaction_date":null,"transaction_amount":null,'
            '"dispute_reason":null,"transactions":[],"confidence":{}}.'
        )
    if schema_name == "granite_real_estate_title_seller_info.v1":
        return (
            'Use shape {"seller_name":null,"property_address":null,'
            '"title_company":null,"file_number":null,"closing_date":null,'
            '"confidence":{}}.'
        )
    if schema_name == "granite_mortgage_escrow_statement.v1":
        return (
            'Use shape {"loan_number":null,"servicer_name":null,'
            '"statement_date":null,"escrow_balance":null,"payment_amount":null,'
            '"tax_amount":null,"insurance_amount":null,"confidence":{}}.'
        )
    if schema_name == "granite_receipt_payment_summary.v1":
        return (
            'Use shape {"merchant_name":null,"transaction_date":null,'
            '"subtotal":null,"tax":null,"tip":null,'
            '"discount_total":null,"total":null,'
            '"payment_method":null,"confidence":{}}.'
        )
    if schema_name == "granite_payment_summary.v1":
        return (
            'Use shape {"invoice_no":null,"amount":null,"payments":[],'
            '"confidence":{}}. Include at most two payment objects.'
        )
    if schema_name == "granite_healthcare_coverage_decision.v1":
        return (
            'Use shape {"facts":[{"name":"denial_reason","value":null,'
            '"confidence":0.0,"source_text":null}],"contacts":[],'
            '"service_lines":[],"warnings":[]}.'
        )
    return "Use the compact object shape defined by the supplied API response schema."
