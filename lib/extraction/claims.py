from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from lib.extraction.claim_registry import (
    claim_key_is_admissible,
    claim_value_type_is_admissible,
)
from lib.extraction.region_envelope import (
    EvidenceRef,
    RegionExtractionEnvelope,
    RegionFact,
    RegionLineItem,
)

ClaimSourceEngine = Literal["docling", "granite"]
ClaimValueType = Literal[
    "money",
    "date",
    "quantity",
    "identifier",
    "party",
    "enum",
    "text",
    "number",
    "boolean",
    "object",
]


@dataclass(frozen=True)
class ClaimAnchor:
    page_number: int | None = None
    page_id: str | None = None
    docling_element_ids: tuple[str, ...] = ()
    table_id: str | None = None
    row_index: int | None = None
    bbox: tuple[float, ...] | None = None
    text_span: dict[str, Any] | None = None
    semantic_region_id: str | None = None

    def as_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "docling_element_ids": list(self.docling_element_ids),
        }
        for key, value in (
            ("page_number", self.page_number),
            ("page_id", self.page_id),
            ("table_id", self.table_id),
            ("row_index", self.row_index),
            ("bbox", list(self.bbox) if self.bbox is not None else None),
            ("text_span", self.text_span),
            ("semantic_region_id", self.semantic_region_id),
        ):
            if value not in (None, "", []):
                payload[key] = value
        return payload


@dataclass(frozen=True)
class Claim:
    claim_id: str
    document_id: str
    source_engine: ClaimSourceEngine
    anchor: ClaimAnchor
    canonical_key: str
    raw_value: str
    typed_value: Any
    value_type: ClaimValueType
    confidence: float | None
    method: str
    group_id: str | None = None
    evidence: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def as_json(self) -> dict[str, Any]:
        payload = {
            "claim_id": self.claim_id,
            "document_id": self.document_id,
            "source_engine": self.source_engine,
            "anchor": self.anchor.as_json(),
            "canonical_key": self.canonical_key,
            "raw_value": self.raw_value,
            "typed_value": self.typed_value,
            "value_type": self.value_type,
            "method": self.method,
            "evidence": list(self.evidence),
        }
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        if self.group_id is not None:
            payload["group_id"] = self.group_id
        return payload


def claims_from_region_envelope(envelope: RegionExtractionEnvelope) -> list[Claim]:
    claims: list[Claim] = []
    method = envelope.model_output_schema_name
    for fact in envelope.facts:
        claim = _claim_from_fact(
            fact,
            document_id=envelope.document_id,
            method=method,
            group_id=None,
        )
        if claim is not None:
            claims.append(claim)
    for ordinal, item in enumerate(envelope.line_items, start=1):
        claims.extend(
            _claims_from_line_item(
                item,
                document_id=envelope.document_id,
                method=method,
                ordinal=ordinal,
                target_schema=_claim_target_schema(envelope),
            )
        )
    for observation in envelope.observations:
        claim = _claim_from_fact(
            observation,
            document_id=envelope.document_id,
            method=method,
            group_id=None,
        )
        if claim is not None:
            claims.append(claim)
    return claims


def claim_anchor_from_evidence(refs: list[EvidenceRef]) -> ClaimAnchor | None:
    for ref in refs:
        anchor = _anchor_from_ref(ref)
        if anchor is not None:
            return anchor
    return None


def _claim_from_fact(
    fact: RegionFact,
    *,
    document_id: str,
    method: str,
    group_id: str | None,
) -> Claim | None:
    anchor = claim_anchor_from_evidence(fact.evidence)
    if anchor is None:
        return None
    if not claim_key_is_admissible(fact.name):
        return None
    typed = _typed_value(fact.value_type, fact.value)
    if typed is None:
        return None
    if not claim_value_type_is_admissible(fact.name, typed[0]):
        return None
    source_engine = _source_engine(fact.evidence)
    if source_engine is None:
        return None
    return _claim(
        document_id=document_id,
        source_engine=source_engine,
        anchor=anchor,
        canonical_key=fact.name,
        raw_value=_raw_value(fact),
        typed_value=typed[1],
        value_type=typed[0],
        confidence=fact.confidence,
        method=method,
        group_id=group_id,
        evidence=tuple(ref.model_dump(mode="json", exclude_none=True) for ref in fact.evidence),
    )


def _claims_from_line_item(
    item: RegionLineItem,
    *,
    document_id: str,
    method: str,
    ordinal: int,
    target_schema: str | None,
) -> list[Claim]:
    anchor = claim_anchor_from_evidence(item.evidence)
    if anchor is None:
        return []
    group_id = _group_id(document_id, anchor, ordinal)
    source_engine = _source_engine(item.evidence)
    if source_engine is None:
        return []
    evidence = tuple(ref.model_dump(mode="json", exclude_none=True) for ref in item.evidence)
    prefix = _line_item_prefix(target_schema)
    raw_fields: tuple[tuple[str, Any, ClaimValueType], ...] = (
        ("description", item.description, "text"),
        ("code", item.code, "identifier"),
        ("quantity", item.quantity, "number"),
        ("unit", item.unit, "text"),
        ("unit_price", _money(item.unit_price, item.currency_code), "money"),
        ("gross_amount", _money(item.gross_amount, item.currency_code), "money"),
        ("tax_amount", _money(item.tax_amount, item.currency_code), "money"),
        ("amount", _money(item.net_amount, item.currency_code), "money"),
        ("service_date", item.service_date, "date"),
        ("category_hint", item.category_hint, "text"),
    )
    claims: list[Claim] = []
    for field_name, value, value_type in raw_fields:
        typed = _typed_value(value_type, value)
        if typed is None:
            continue
        canonical_key = f"{prefix}.{field_name}"
        if not claim_value_type_is_admissible(canonical_key, typed[0]):
            continue
        claims.append(
            _claim(
                document_id=document_id,
                source_engine=source_engine,
                anchor=anchor,
                canonical_key=canonical_key,
                raw_value=_stable_json(value),
                typed_value=typed[1],
                value_type=typed[0],
                confidence=item.confidence,
                method=method,
                group_id=group_id,
                evidence=evidence,
            )
        )
    return claims


def _claim(
    *,
    document_id: str,
    source_engine: ClaimSourceEngine,
    anchor: ClaimAnchor,
    canonical_key: str,
    raw_value: str,
    typed_value: Any,
    value_type: ClaimValueType,
    confidence: float | None,
    method: str,
    group_id: str | None,
    evidence: tuple[dict[str, Any], ...],
) -> Claim:
    claim_id = _claim_id(
        document_id=document_id,
        anchor=anchor,
        canonical_key=canonical_key,
        typed_value=typed_value,
    )
    return Claim(
        claim_id=claim_id,
        document_id=document_id,
        source_engine=source_engine,
        anchor=anchor,
        canonical_key=canonical_key,
        raw_value=raw_value,
        typed_value=typed_value,
        value_type=value_type,
        confidence=confidence,
        method=method,
        group_id=group_id,
        evidence=evidence,
    )


def _line_item_prefix(target_schema: str | None) -> str:
    if target_schema in {"invoice", "receipt", "medical_eob", "service_record", "retail_order"}:
        return f"{target_schema}.line_item"
    return "line_item"


def _claim_target_schema(envelope: RegionExtractionEnvelope) -> str | None:
    if envelope.resolved_document_type in {"service_record", "retail_order"}:
        return envelope.resolved_document_type
    return envelope.target_schema or envelope.resolved_document_type


def _anchor_from_ref(ref: EvidenceRef) -> ClaimAnchor | None:
    if ref.page_number is None and ref.page_id in (None, ""):
        return None
    element_ids = tuple(str(ref.element_id).split(",")) if ref.element_id else ()
    has_structural_locator = (
        bool(element_ids)
        or ref.table_id not in (None, "")
        or ref.bbox is not None
        or ref.text_span is not None
    )
    if not has_structural_locator:
        return None
    return ClaimAnchor(
        page_number=ref.page_number,
        page_id=ref.page_id,
        docling_element_ids=element_ids,
        table_id=ref.table_id,
        row_index=ref.row_index,
        bbox=tuple(ref.bbox) if ref.bbox is not None else None,
        text_span=ref.text_span,
        semantic_region_id=ref.semantic_region_id,
    )


def _typed_value(value_type: str, value: Any) -> tuple[ClaimValueType, Any] | None:
    if value in (None, ""):
        return None
    normalized_type = value_type.strip().lower()
    if normalized_type == "money":
        if not isinstance(value, dict) or value.get("amount") is None:
            return None
        try:
            amount = float(value["amount"])
        except (TypeError, ValueError):
            return None
        payload: dict[str, Any] = {"amount": amount}
        currency = value.get("currency") or value.get("currency_code")
        if currency not in (None, ""):
            payload["currency"] = str(currency).upper()
        return "money", payload
    if normalized_type == "date":
        if not isinstance(value, str) or not _is_date_like(value):
            return None
        return "date", value
    if normalized_type in {"number", "quantity"}:
        if not isinstance(value, int | float):
            return None
        if normalized_type == "quantity":
            return "quantity", float(value)
        return "number", float(value)
    if normalized_type == "boolean":
        if not isinstance(value, bool):
            return None
        return "boolean", value
    if normalized_type in {"string", "text", "identifier", "enum", "party"}:
        text = " ".join(str(value).strip().split())
        if not text:
            return None
        if normalized_type == "identifier":
            return "identifier", text
        if normalized_type == "enum":
            return "enum", text
        if normalized_type == "party":
            return "party", text
        return "text", text
    if normalized_type in {"object", "array"}:
        if not isinstance(value, dict | list):
            return None
        return "object", value
    return None


def _money(amount: float | None, currency: str | None) -> dict[str, Any] | None:
    if amount is None:
        return None
    payload: dict[str, Any] = {"amount": amount}
    if currency not in (None, ""):
        payload["currency"] = currency
    return payload


def _raw_value(fact: RegionFact) -> str:
    if fact.source_text:
        return fact.source_text
    return _stable_json(fact.value)


def _source_engine(refs: list[EvidenceRef]) -> ClaimSourceEngine | None:
    source_engine = refs[0].source_engine if refs else ""
    normalized = source_engine.strip().lower()
    if normalized.startswith("granite"):
        return "granite"
    if normalized.startswith("docling"):
        return "docling"
    return None


def _group_id(document_id: str, anchor: ClaimAnchor, ordinal: int) -> str:
    return _sha256(
        {
            "document_id": document_id,
            "anchor": anchor.as_json(),
            "ordinal": ordinal,
        }
    )


def _claim_id(
    *,
    document_id: str,
    anchor: ClaimAnchor,
    canonical_key: str,
    typed_value: Any,
) -> str:
    return _sha256(
        {
            "document_id": document_id,
            "anchor": anchor.as_json(),
            "canonical_key": canonical_key,
            "typed_value": typed_value,
        }
    )


def _stable_json(value: Any) -> str:
    return json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    return value


def _is_date_like(value: str) -> bool:
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            datetime.strptime(text, fmt)
            return True
        except ValueError:
            continue
    return False
