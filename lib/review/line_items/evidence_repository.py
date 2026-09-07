"""Prove recorded locator existence, without claiming independent pixel support."""

from typing import Any
from uuid import UUID

from lib.contracts.line_item_authority import LineEvidenceRef


def evidence_is_bound(
    cur: Any, document_id: UUID, raw: list[dict[str, Any]], refs: list[LineEvidenceRef]
) -> bool:
    for item, ref in zip(raw, refs, strict=True):
        declared_document = item.get("document_id", item.get("documentId"))
        if declared_document is not None and str(declared_document) != str(document_id):
            return False
        cur.execute(
            "SELECT id,text_content FROM document_pages WHERE document_id=%s AND page_number=%s",
            (document_id, ref.page_number),
        )
        page = cur.fetchone()
        if page is None:
            return False
        declared_page = item.get("page_id", item.get("pageId"))
        if declared_page is not None and str(declared_page) != str(page["id"]):
            return False
        if not _locator_exists(cur, document_id, page, ref):
            return False
    return True


def _locator_exists(
    cur: Any, document_id: UUID, page: dict[str, Any], ref: LineEvidenceRef
) -> bool:
    element = None
    if ref.element_id:
        cur.execute(
            "SELECT id,text_content FROM document_elements "
            "WHERE id=%s AND document_id=%s AND page_id=%s",
            (ref.element_id, document_id, page["id"]),
        )
        element = cur.fetchone()
        if element is None:
            return False
    table_row = False
    if ref.table_id:
        cur.execute(
            "SELECT id,row_count,column_count FROM document_tables "
            "WHERE id=%s AND document_id=%s AND page_id=%s",
            (ref.table_id, document_id, page["id"]),
        )
        table = cur.fetchone()
        if table is None:
            return False
        if ref.row_index is not None:
            if table["row_count"] is None or ref.row_index >= table["row_count"]:
                return False
            table_row = True
        if ref.column_index is not None and (
            table["column_count"] is None or ref.column_index >= table["column_count"]
        ):
            return False
    elif ref.row_index is not None or ref.column_index is not None:
        return False
    independent = ref.bbox is not None or element is not None or table_row
    page_text = page["text_content"]
    unique_text = bool(
        ref.source_text and isinstance(page_text, str) and page_text.count(ref.source_text) == 1
    )
    span = ref.text_span
    if span is not None:
        if span.basis == "page_text":
            if not _span_in_text(page_text, span.start, span.end):
                return False
            return True
        if span.basis == "element_text":
            if element is None or not _span_in_text(element["text_content"], span.start, span.end):
                return False
            return True
        # This DTO has no immutable chunk/raw-output artifact identity. Those
        # spans (and an unspecified basis) cannot independently locate a source.
        return independent or unique_text
    return independent or unique_text


def _span_in_text(value: object, start: int, end: int) -> bool:
    return (
        isinstance(value, str) and 0 <= start < end <= len(value) and bool(value[start:end].strip())
    )
