from __future__ import annotations

import re
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
        "due_date": ("due date",),
    },
    "receipt": {
        "receipt": ("receipt",),
        "subtotal": ("subtotal",),
        "tax": ("tax", "sales tax"),
        "paid": ("paid", "amount paid"),
        "payment": ("payment",),
    },
    "service_record": {
        "repair_order": ("repair order", "r/o", "ro open date", "rio open date"),
        "service": ("service", "services", "labor"),
        "parts": ("parts", "part number"),
        "vehicle": ("vin", "mileage", "mileage in", "vehicle"),
        "motorcycle": ("motorcycle", "motorcycles"),
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
        "dispute": ("dispute", "reason for dispute", "dispute form"),
        "transaction": ("transaction",),
        "charge": ("charge",),
        "unauthorized": ("unauthorized", "not authorized"),
        "chargeback": ("chargeback",),
        "fraud": ("fraud", "fraudulent"),
    },
}


@dataclass(frozen=True)
class AnchorSpec:
    required_any: frozenset[str] = frozenset()
    required_all: frozenset[str] = frozenset()
    negative_any: tuple[str, ...] = ()
    threshold: int = 2


ANCHOR_SPECS: dict[str, AnchorSpec] = {
    "medical_eob": AnchorSpec(threshold=2),
    "invoice": AnchorSpec(required_any=frozenset({"invoice", "amount_due"}), threshold=2),
    "receipt": AnchorSpec(
        required_any=frozenset({"receipt", "subtotal", "paid"}),
        negative_any=("explanation of benefits", "claim number"),
        threshold=2,
    ),
    "service_record": AnchorSpec(
        required_any=frozenset({"repair_order", "service"}),
        threshold=3,
    ),
    "retail_order": AnchorSpec(required_any=frozenset({"order", "ship_to", "bh_photo"})),
    "real_estate_title": AnchorSpec(
        required_any=frozenset({"title", "seller", "closing"}),
        threshold=2,
    ),
    "mortgage_escrow_statement": AnchorSpec(
        required_any=frozenset({"escrow"}),
        threshold=2,
    ),
    "financial_dispute_form": AnchorSpec(
        required_any=frozenset({"dispute", "unauthorized", "chargeback", "fraud"}),
        threshold=2,
    ),
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
    table_signal: str
    weak_signal_reason: str | None = None


@dataclass(frozen=True)
class DoclingAudit:
    document_id: UUID
    page_count: int
    element_count: int
    table_count: int
    page_snippets: tuple[PageAuditSnippet, ...]
    table_summaries: tuple[TableAuditSummary, ...]
    lexical_anchors: tuple[str, ...]
    anchor_counts: dict[str, int]
    suggested_family_hints: tuple[str, ...]
    family_tension: tuple[str, ...]

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
    suggested_family_hints = tuple(
        family
        for family in FAMILY_ANCHORS
        if family_has_suggested_hint(family, anchor_hits.get(family, ()))
    )
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
        anchor_counts={family: len(anchors) for family, anchors in anchor_hits.items()},
        suggested_family_hints=suggested_family_hints,
        family_tension=_family_tension(suggested_family_hints),
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
    return family_anchor_hits_from_text(audit_text)


def family_anchor_hits_from_text(text: str) -> dict[str, tuple[str, ...]]:
    return _anchor_hits(_normalized_text(text))


def family_has_required_hint_fit(family: str, anchors: tuple[str, ...]) -> bool:
    spec = ANCHOR_SPECS.get(family, AnchorSpec())
    anchor_set = set(anchors)
    if spec.required_all and not spec.required_all.issubset(anchor_set):
        return False
    if spec.required_any and not spec.required_any.intersection(anchor_set):
        return False
    return True


def family_has_suggested_hint(family: str, anchors: tuple[str, ...]) -> bool:
    spec = ANCHOR_SPECS.get(family, AnchorSpec())
    return len(anchors) >= spec.threshold and family_has_required_hint_fit(family, anchors)


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
            table_signal=_table_signal(table.table_markdown, table.table_json),
            weak_signal_reason=_weak_table_signal_reason(table.table_markdown, table.table_json),
        )
        for table in source.tables
    ]


def _table_signal(table_markdown: str | None, table_json: dict[str, Any]) -> str:
    row_count = _markdown_row_count(table_markdown)
    json_row_count = _table_json_row_count(table_json)
    if row_count >= 2 or json_row_count >= 2 or (row_count >= 1 and json_row_count >= 1):
        return "strong"
    if (table_markdown or "").strip() or table_json:
        return "weak"
    return "none"


def _weak_table_signal_reason(
    table_markdown: str | None,
    table_json: dict[str, Any],
) -> str | None:
    signal = _table_signal(table_markdown, table_json)
    if signal != "weak":
        return None
    if not (table_markdown or "").strip():
        return "missing_markdown"
    if _markdown_row_count(table_markdown) < 2:
        return "too_few_markdown_rows"
    if table_json and _table_json_row_count(table_json) < 2:
        return "too_few_json_rows"
    return "weak_table_structure"


def _markdown_row_count(table_markdown: str | None) -> int:
    if not table_markdown:
        return 0
    return sum(1 for line in table_markdown.splitlines() if "|" in line and line.strip("| "))


def _table_json_row_count(table_json: dict[str, Any]) -> int:
    rows = table_json.get("rows") if isinstance(table_json, dict) else None
    return len(rows) if isinstance(rows, list) else 0


def _anchor_hits(text: str) -> dict[str, tuple[str, ...]]:
    hits: dict[str, tuple[str, ...]] = {}
    for family, anchors in FAMILY_ANCHORS.items():
        spec = ANCHOR_SPECS.get(family, AnchorSpec())
        if any(_contains_phrase(text, phrase) for phrase in spec.negative_any):
            continue
        family_hits = [
            anchor
            for anchor, patterns in anchors.items()
            if any(_contains_phrase(text, pattern) for pattern in patterns)
        ]
        if family_hits:
            hits[family] = tuple(sorted(family_hits))
    return hits


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized = re.escape(_normalized_text(phrase))
    return re.search(rf"(?<!\w){normalized}(?!\w)", text) is not None


def _family_tension(suggested_family_hints: tuple[str, ...]) -> tuple[str, ...]:
    if len(suggested_family_hints) <= 1:
        return ()
    return tuple(suggested_family_hints)


def _normalized_text(value: str) -> str:
    return " ".join(value.lower().replace("&", " & ").split())


def _snippet(value: str, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "..."
