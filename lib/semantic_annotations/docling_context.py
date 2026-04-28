from __future__ import annotations

from typing import Any

from lib.extraction.models import (
    ExtractionSourceDocument,
    ParsedElementText,
    ParsedPageText,
    ParsedTableText,
)

PAGE_SNIPPET_CHARS = 320
ELEMENT_SNIPPET_CHARS = 240
TABLE_SNIPPET_CHARS = 320


def build_docling_context(source: ExtractionSourceDocument) -> dict[str, Any]:
    elements_by_page = _group_elements_by_page(source.elements)
    tables_by_page = _group_tables_by_page(source.tables)
    return {
        "documentId": str(source.document_id),
        "family": source.family,
        "subtype": source.subtype,
        "title": source.title,
        "counterpartyDisplay": source.counterparty_display,
        "quality": source.metadata.get("phase8", {}).get("quality", {}),
        "pages": [
            _page_context(
                page,
                elements=elements_by_page.get(page.page_number, []),
                tables=tables_by_page.get(page.page_number, []),
            )
            for page in source.pages
        ],
    }


def _page_context(
    page: ParsedPageText,
    *,
    elements: list[ParsedElementText],
    tables: list[ParsedTableText],
) -> dict[str, Any]:
    return {
        "pageId": str(page.page_id),
        "pageNumber": page.page_number,
        "imageSha256": page.image_sha256,
        "textSnippet": _snippet(page.text, PAGE_SNIPPET_CHARS),
        "elements": [_element_context(element) for element in elements],
        "tables": [_table_context(table) for table in tables],
    }


def _element_context(element: ParsedElementText) -> dict[str, Any]:
    return {
        "elementId": str(element.element_id),
        "pageNumber": element.page_number,
        "ordinal": element.ordinal,
        "bbox": element.bbox,
        "textSnippet": _snippet(element.text, ELEMENT_SNIPPET_CHARS),
    }


def _table_context(table: ParsedTableText) -> dict[str, Any]:
    return {
        "tableId": str(table.table_id),
        "pageNumber": table.page_number,
        "tableIndex": table.table_index,
        "markdownSnippet": _snippet(table.table_markdown or "", TABLE_SNIPPET_CHARS),
        "hasTableJson": bool(table.table_json),
    }


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
