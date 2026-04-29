from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

from lib.extraction.models import ExtractionSourceDocument

SNIPPET_CHARS = 360
TABLE_SNIPPET_CHARS = 360

FAMILY_ANCHORS: dict[str, dict[str, tuple[str, ...]]] = {
    "medical_eob": {
        "eob": ("eob", "explanation of benefits"),
        "claim": ("claim", "claim number"),
        "patient_responsibility": ("patient responsibility",),
        "anthem": ("anthem",),
        "denial": ("denial", "denied"),
    },
    "invoice": {
        "invoice": ("invoice", "invoice number"),
        "amount_due": ("amount due", "balance due"),
        "bill_to": ("bill to",),
    },
    "receipt": {
        "receipt": ("receipt",),
        "subtotal": ("subtotal",),
        "tax": ("tax", "sales tax"),
        "paid": ("paid", "amount paid"),
        "payment": ("payment",),
    },
    "retail_order": {
        "order": ("order", "order number"),
        "ship_to": ("ship to", "shipping address"),
        "bh_photo": ("b&h", "bh photo", "b h photo"),
    },
    "real_estate_title": {
        "title": ("title", "title company"),
        "seller": ("seller", "seller information", "seller proceeds"),
        "closing": ("closing", "settlement"),
    },
    "mortgage_escrow_statement": {
        "escrow": ("escrow",),
        "mortgage": ("mortgage",),
        "shortage": ("shortage",),
        "surplus": ("surplus",),
        "uwm": ("uwm", "united wholesale mortgage"),
    },
    "financial_dispute_form": {
        "dispute": ("dispute",),
        "transaction": ("transaction",),
        "charge": ("charge",),
        "unauthorized": ("unauthorized",),
    },
}


@dataclass(frozen=True)
class PageAuditSnippet:
    page_id: UUID
    page_number: int
    text_snippet: str
    element_count: int
    table_count: int


@dataclass(frozen=True)
class TableAuditSummary:
    table_id: UUID
    page_number: int
    table_index: int
    markdown_snippet: str
    has_table_json: bool


@dataclass(frozen=True)
class DoclingAudit:
    document_id: UUID
    page_count: int
    element_count: int
    table_count: int
    page_snippets: tuple[PageAuditSnippet, ...]
    table_summaries: tuple[TableAuditSummary, ...]
    lexical_anchors: tuple[str, ...]
    suggested_family_hints: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["document_id"] = str(self.document_id)
        for page in payload["page_snippets"]:
            page["page_id"] = str(page["page_id"])
        for table in payload["table_summaries"]:
            table["table_id"] = str(table["table_id"])
        return payload


def build_docling_audit(source: ExtractionSourceDocument) -> DoclingAudit:
    text = _normalized_text(
        " ".join(
            [
                source.title,
                source.original_filename or "",
                source.counterparty_display or "",
                source.full_text,
                " ".join(table.table_markdown or "" for table in source.tables),
            ]
        )
    )
    anchor_hits = _anchor_hits(text)
    return DoclingAudit(
        document_id=source.document_id,
        page_count=len(source.pages),
        element_count=len(source.elements),
        table_count=len(source.tables),
        page_snippets=tuple(_page_snippets(source)),
        table_summaries=tuple(_table_summaries(source)),
        lexical_anchors=tuple(
            sorted({anchor for anchors in anchor_hits.values() for anchor in anchors})
        ),
        suggested_family_hints=tuple(
            family
            for family in FAMILY_ANCHORS
            if len(anchor_hits.get(family, ())) >= _hint_threshold(family)
        ),
    )


def family_anchor_hits(source: ExtractionSourceDocument) -> dict[str, tuple[str, ...]]:
    audit_text = _normalized_text(
        " ".join(
            [
                source.title,
                source.original_filename or "",
                source.counterparty_display or "",
                source.full_text,
                " ".join(table.table_markdown or "" for table in source.tables),
            ]
        )
    )
    return _anchor_hits(audit_text)


def _page_snippets(source: ExtractionSourceDocument) -> list[PageAuditSnippet]:
    elements_by_page: dict[int, int] = {}
    tables_by_page: dict[int, int] = {}
    for element in source.elements:
        elements_by_page[element.page_number] = elements_by_page.get(element.page_number, 0) + 1
    for table in source.tables:
        tables_by_page[table.page_number] = tables_by_page.get(table.page_number, 0) + 1
    return [
        PageAuditSnippet(
            page_id=page.page_id,
            page_number=page.page_number,
            text_snippet=_snippet(page.text, SNIPPET_CHARS),
            element_count=elements_by_page.get(page.page_number, 0),
            table_count=tables_by_page.get(page.page_number, 0),
        )
        for page in source.pages
    ]


def _table_summaries(source: ExtractionSourceDocument) -> list[TableAuditSummary]:
    return [
        TableAuditSummary(
            table_id=table.table_id,
            page_number=table.page_number,
            table_index=table.table_index,
            markdown_snippet=_snippet(table.table_markdown or "", TABLE_SNIPPET_CHARS),
            has_table_json=bool(table.table_json),
        )
        for table in source.tables
    ]


def _anchor_hits(text: str) -> dict[str, tuple[str, ...]]:
    hits: dict[str, tuple[str, ...]] = {}
    for family, anchors in FAMILY_ANCHORS.items():
        family_hits = [
            anchor
            for anchor, patterns in anchors.items()
            if any(pattern in text for pattern in patterns)
        ]
        if family_hits:
            hits[family] = tuple(sorted(family_hits))
    return hits


def _hint_threshold(family: str) -> int:
    if family in {"real_estate_title", "mortgage_escrow_statement"}:
        return 1
    return 2


def _normalized_text(value: str) -> str:
    return " ".join(value.lower().replace("&", " & ").split())


def _snippet(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "..."
