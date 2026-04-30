from __future__ import annotations

from typing import Any

from lib.extraction.models import (
    ExtractionSourceDocument,
    ParsedElementText,
    ParsedPageText,
    ParsedTableText,
)
from lib.semantic_annotations.docling_audit import TableAuditSummary, build_docling_audit

PAGE_SNIPPET_CHARS = 320
ELEMENT_SNIPPET_CHARS = 160
TABLE_SNIPPET_CHARS = 320
MAX_ELEMENTS_PER_PAGE = 48


def build_docling_context(
    source: ExtractionSourceDocument,
    *,
    focus_page_numbers: set[int] | None = None,
    include_pages_alias: bool = True,
    include_page_image_hashes: bool = True,
    include_element_bboxes: bool = True,
) -> dict[str, Any]:
    elements_by_page = _group_elements_by_page(source.elements)
    tables_by_page = _group_tables_by_page(source.tables)
    audit = build_docling_audit(source)
    table_audit_by_id = {str(table.table_id): table for table in audit.table_summaries}
    focus_pages = [
        page
        for page in source.pages
        if focus_page_numbers is None or page.page_number in focus_page_numbers
    ]
    focus_context = [
        _page_context(
            page,
            elements=elements_by_page.get(page.page_number, []),
            tables=tables_by_page.get(page.page_number, []),
            include_page_image_hash=include_page_image_hashes,
            include_element_bboxes=include_element_bboxes,
        )
        for page in focus_pages
    ]
    document_context: dict[str, Any] = {
        "documentId": str(source.document_id),
        "family": source.family,
        "subtype": source.subtype,
        "title": source.title,
        "originalFilename": source.original_filename,
        "counterpartyDisplay": source.counterparty_display,
        "quality": source.metadata.get("phase8", {}).get("quality", {}),
        "pageCount": len(source.pages),
        "elementCount": len(source.elements),
        "tableCount": len(source.tables),
        "lexicalAnchors": list(audit.lexical_anchors),
        "anchorCounts": audit.anchor_counts,
        "suggestedFamilyHints": list(audit.suggested_family_hints),
        "familyTension": list(audit.family_tension),
        "firstPageSnippet": _snippet(source.pages[0].text, PAGE_SNIPPET_CHARS)
        if source.pages
        else "",
        "lastPageSnippet": _snippet(source.pages[-1].text, PAGE_SNIPPET_CHARS)
        if source.pages
        else "",
        "pageOutline": [
            {
                "pageId": str(page.page_id),
                "pageNumber": page.page_number,
                "outlineRole": _outline_role(
                    page.page_number,
                    page_count=len(source.pages),
                    focus_page_numbers=focus_page_numbers,
                ),
                "textSnippet": _snippet(page.text, PAGE_SNIPPET_CHARS),
                "elementCount": len(elements_by_page.get(page.page_number, [])),
                "tableCount": len(tables_by_page.get(page.page_number, [])),
            }
            for page in source.pages
        ],
        "tableInventory": [
            _table_inventory_context(table, table_audit_by_id.get(str(table.table_id)))
            for table in source.tables
        ],
        "focusPageContract": _focus_page_contract(focus_pages, focus_page_numbers),
    }
    context: dict[str, Any] = {
        "document": document_context,
        "focusPages": focus_context,
    }
    if include_pages_alias:
        context["pages"] = focus_context
    return context


def _page_context(
    page: ParsedPageText,
    *,
    elements: list[ParsedElementText],
    tables: list[ParsedTableText],
    include_page_image_hash: bool,
    include_element_bboxes: bool,
) -> dict[str, Any]:
    bounded_elements = sorted(elements, key=lambda element: element.ordinal)[:MAX_ELEMENTS_PER_PAGE]
    context = {
        "pageId": str(page.page_id),
        "pageNumber": page.page_number,
        "textSnippet": _snippet(page.text, PAGE_SNIPPET_CHARS),
        "elementCount": len(elements),
        "elementsTruncated": max(0, len(elements) - len(bounded_elements)),
        "elements": [
            _element_context(element, include_bbox=include_element_bboxes)
            for element in bounded_elements
        ],
        "tables": [_table_context(table) for table in tables],
    }
    if include_page_image_hash:
        context["imageSha256"] = page.image_sha256
    return context


def _element_context(element: ParsedElementText, *, include_bbox: bool) -> dict[str, Any]:
    context = {
        "elementId": str(element.element_id),
        "pageNumber": element.page_number,
        "ordinal": element.ordinal,
        "textSnippet": _snippet(element.text, ELEMENT_SNIPPET_CHARS),
    }
    if include_bbox:
        context["bbox"] = element.bbox
    return context


def _table_context(table: ParsedTableText) -> dict[str, Any]:
    table_signal = _table_signal(table)
    return {
        "tableId": str(table.table_id),
        "pageNumber": table.page_number,
        "tableIndex": table.table_index,
        "markdownSnippet": _snippet(table.table_markdown or "", TABLE_SNIPPET_CHARS),
        "hasTableJson": bool(table.table_json),
        "tableSignal": table_signal,
        "weakSignalReason": _weak_table_signal_reason(table) if table_signal == "weak" else None,
    }


def _table_inventory_context(
    table: ParsedTableText,
    audit_summary: TableAuditSummary | None,
) -> dict[str, Any]:
    return {
        "tableId": str(table.table_id),
        "pageNumber": table.page_number,
        "tableIndex": table.table_index,
        "markdownSnippet": _snippet(table.table_markdown or "", TABLE_SNIPPET_CHARS),
        "hasTableJson": bool(table.table_json),
        "tableSignal": audit_summary.table_signal if audit_summary is not None else "unknown",
        "weakSignalReason": audit_summary.weak_signal_reason if audit_summary is not None else None,
    }


def _focus_page_contract(
    focus_pages: list[ParsedPageText],
    focus_page_numbers: set[int] | None,
) -> dict[str, Any]:
    return {
        "allowedPageIds": [str(page.page_id) for page in focus_pages],
        "allowedPageNumbers": [page.page_number for page in focus_pages],
        "pagesArrayMustMatchFocusPages": focus_page_numbers is not None,
        "pageOutlineIsContextOnly": focus_page_numbers is not None,
    }


def _outline_role(
    page_number: int,
    *,
    page_count: int,
    focus_page_numbers: set[int] | None,
) -> str:
    roles: list[str] = []
    if page_number == 1:
        roles.append("first")
    if page_number == page_count:
        roles.append("last")
    if focus_page_numbers is not None and page_number in focus_page_numbers:
        roles.append("focus")
    return "+".join(roles) if roles else "middle"


def _table_signal(table: ParsedTableText) -> str:
    markdown_rows = _markdown_row_count(table.table_markdown)
    json_rows = _table_json_row_count(table.table_json)
    if markdown_rows >= 2 or json_rows >= 2 or (markdown_rows >= 1 and json_rows >= 1):
        return "strong"
    if (table.table_markdown or "").strip() or table.table_json:
        return "weak"
    return "none"


def _weak_table_signal_reason(table: ParsedTableText) -> str | None:
    if not (table.table_markdown or "").strip():
        return "missing_markdown"
    if _markdown_row_count(table.table_markdown) < 2:
        return "too_few_markdown_rows"
    if table.table_json and _table_json_row_count(table.table_json) < 2:
        return "too_few_json_rows"
    return "weak_table_structure"


def _markdown_row_count(table_markdown: str | None) -> int:
    if not table_markdown:
        return 0
    return sum(1 for line in table_markdown.splitlines() if "|" in line and line.strip("| "))


def _table_json_row_count(table_json: dict[str, Any]) -> int:
    rows = table_json.get("rows") if isinstance(table_json, dict) else None
    return len(rows) if isinstance(rows, list) else 0


def _group_elements_by_page(
    elements: list[ParsedElementText],
) -> dict[int, list[ParsedElementText]]:
    grouped: dict[int, list[ParsedElementText]] = {}
    for element in elements:
        grouped.setdefault(element.page_number, []).append(element)
    return grouped


def _group_tables_by_page(tables: list[ParsedTableText]) -> dict[int, list[ParsedTableText]]:
    grouped: dict[int, list[ParsedTableText]] = {}
    for table in tables:
        grouped.setdefault(table.page_number, []).append(table)
    return grouped


def _snippet(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"
