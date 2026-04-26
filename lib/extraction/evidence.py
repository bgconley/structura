from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lib.extraction.models import Evidence, ExtractionSourceDocument, ParsedElementText


@dataclass(frozen=True)
class EvidenceResolver:
    source: ExtractionSourceDocument

    def for_value(self, value: object, *, source_engine: str = "docling") -> list[Evidence]:
        text = _string_value(value)
        if not text:
            return self.first_page_evidence(source_engine=source_engine)

        lowered = text.lower()
        for element in self.source.elements:
            if element.text and lowered in element.text.lower():
                return [_element_evidence(element, source_text=text, source_engine=source_engine)]

        for page in self.source.pages:
            start = page.text.lower().find(lowered)
            if start >= 0:
                return [
                    {
                        "page_number": page.page_number,
                        "source_engine": source_engine,
                        "source_text": text,
                        "text_span": {
                            "start": start,
                            "end": start + len(text),
                            "basis": "page_text",
                        },
                        "confidence": 0.82,
                    }
                ]

        return self.first_page_evidence(source_engine=source_engine, source_text=text)

    def first_page_evidence(
        self,
        *,
        source_engine: str = "docling",
        source_text: str | None = None,
    ) -> list[Evidence]:
        page = self.source.pages[0] if self.source.pages else None
        if not page:
            return []
        excerpt = source_text or page.text[:120] or self.source.title
        return [
            {
                "page_number": page.page_number,
                "source_engine": source_engine,
                "source_text": excerpt,
                "text_span": {
                    "start": 0,
                    "end": min(len(page.text), max(len(excerpt), 1)),
                    "basis": "page_text",
                },
                "confidence": 0.72,
            }
        ]


def has_concrete_evidence(evidence: list[Evidence] | None) -> bool:
    if not evidence:
        return False
    return any(is_concrete_evidence_ref(item) for item in evidence)


def is_concrete_evidence_ref(item: Evidence) -> bool:
    if not item.get("page_number"):
        return False
    if item.get("bbox") is not None or item.get("element_id") is not None:
        return True
    if item.get("table_id") is not None and item.get("row_index") is not None:
        return True
    if item.get("text_span") is not None:
        return True
    return bool(item.get("source_text"))


def _element_evidence(
    element: ParsedElementText,
    *,
    source_text: str,
    source_engine: str,
) -> Evidence:
    evidence: Evidence = {
        "page_number": element.page_number,
        "element_id": str(element.element_id),
        "source_engine": source_engine,
        "source_text": source_text,
        "confidence": 0.86,
    }
    bbox = _normalize_bbox(element.bbox)
    if bbox:
        evidence["bbox"] = bbox
    return evidence


def _normalize_bbox(value: Any) -> list[float] | None:
    if isinstance(value, list) and len(value) == 4:
        return [float(item) for item in value]
    if isinstance(value, dict):
        keys = ("l", "t", "r", "b")
        if all(key in value for key in keys):
            return [float(value[key]) for key in keys]
        keys = ("x0", "y0", "x1", "y1")
        if all(key in value for key in keys):
            return [float(value[key]) for key in keys]
    return None


def _string_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        amount = value.get("amount")
        currency = value.get("currency")
        if amount is not None:
            return f"{amount} {currency or ''}".strip()
    return str(value).strip()
