from __future__ import annotations

from typing import Any

from lib.extraction.models import (
    ExtractionSourceDocument,
    ParsedElementText,
    ParsedPageText,
    ParsedTableText,
)
from lib.semantic_annotations.docling_audit import build_docling_audit

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
    context = {
        "document": {
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
            "suggestedFamilyHints": list(audit.suggested_family_hints),
            "pageOutline": [
                {
                    "pageId": str(page.page_id),
                    "pageNumber": page.page_number,
                    "textSnippet": _snippet(page.text, PAGE_SNIPPET_CHARS),
                    "elementCount": len(elements_by_page.get(page.page_number, [])),
                    "tableCount": len(tables_by_page.get(page.page_number, [])),
                }
                for page in source.pages
            ],
            "tableInventory": [
                {
                    "tableId": str(table.table_id),
                    "pageNumber": table.page_number,
                    "tableIndex": table.table_index,
                    "markdownSnippet": _snippet(table.table_markdown or "", TABLE_SNIPPET_CHARS),
                    "hasTableJson": bool(table.table_json),
                }
                for table in source.tables
            ],
        },
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
