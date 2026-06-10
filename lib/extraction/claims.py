from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

from lib.extraction.candidate_value_parsing import date_value
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
        payload = self.identity_json()
        if self.semantic_region_id not in (None, ""):
            payload["semantic_region_id"] = self.semantic_region_id
        return payload

    def identity_json(self) -> dict[str, Any]:
        """Structural anchor identity per ADR 0005: page + Docling locators only.

        semantic_region_id is lineage, not identity; the same Docling anchor
        reached through two different semantic regions must hash identically.
        """
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
    if _planner_only_method(envelope.model_output_schema_name):
        return []
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
    group_ids = _line_item_group_ids(envelope.document_id, envelope.line_items)
    for item, group_id in zip(envelope.line_items, group_ids, strict=True):
        if group_id is None:
            continue
        claims.extend(
            _claims_from_line_item(
                item,
                document_id=envelope.document_id,
                method=method,
                group_id=group_id,
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
    anchors: list[ClaimAnchor] = []
    for ref in refs:
        anchor = _anchor_from_ref(ref)
        if anchor is not None:
            anchors.append(anchor)
    if not anchors:
        return None
    return min(anchors, key=_anchor_selection_key)


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
    source_engine = _source_engine(method, fact.evidence)
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
    group_id: str,
    target_schema: str | None,
) -> list[Claim]:
    anchor = claim_anchor_from_evidence(item.evidence)
    if anchor is None:
        return []
    source_engine = _source_engine(method, item.evidence)
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
        ("allowed_amount", _money(item.allowed_amount, item.currency_code), "money"),
        ("plan_paid", _money(item.plan_paid_amount, item.currency_code), "money"),
        ("discount", _money(item.discount_amount, item.currency_code), "money"),
        ("tax_amount", _money(item.tax_amount, item.currency_code), "money"),
        ("amount", _money(item.net_amount, item.currency_code), "money"),
        ("service_date", item.service_date, "date"),
        ("tax_category_hint", item.tax_category_hint, "text"),
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


def _planner_only_method(method: str) -> bool:
    normalized = method.strip().lower().replace("-", "_")
    return normalized.startswith("qwen")


def _anchor_from_ref(ref: EvidenceRef) -> ClaimAnchor | None:
    if ref.page_number is None and ref.page_id in (None, ""):
        return None
    element_ids = _docling_element_ids(ref.element_id)
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


def _anchor_selection_key(anchor: ClaimAnchor) -> tuple[int, int, str, str, int, str]:
    return (
        -_anchor_specificity(anchor),
        anchor.page_number if anchor.page_number is not None else 1_000_000_000,
        anchor.page_id or "",
        anchor.table_id or "",
        anchor.row_index if anchor.row_index is not None else 1_000_000_000,
        _stable_json(anchor.identity_json()),
    )


def _anchor_specificity(anchor: ClaimAnchor) -> int:
    return sum(
        (
            bool(anchor.docling_element_ids),
            anchor.table_id not in (None, ""),
            anchor.row_index is not None,
            anchor.bbox is not None,
            anchor.text_span is not None,
        )
    )


def _docling_element_ids(element_id: str | None) -> tuple[str, ...]:
    if not element_id:
        return ()
    return tuple(sorted({part.strip() for part in str(element_id).split(",") if part.strip()}))


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
        if not isinstance(value, str):
            return None
        parsed_date = date_value(value)
        if parsed_date is None:
            return None
        return "date", parsed_date.isoformat()
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


def _source_engine(method: str, refs: list[EvidenceRef]) -> ClaimSourceEngine | None:
    method_source = _source_engine_label(method)
    if method_source is not None:
        return method_source
    evidence_sources = {_source_engine_label(ref.source_engine) for ref in refs}
    if "granite" in evidence_sources:
        return "granite"
    if "docling" in evidence_sources:
        return "docling"
    return None


def _source_engine_label(value: str) -> ClaimSourceEngine | None:
    normalized = value.strip().lower()
    if normalized.startswith("granite"):
        return "granite"
    if normalized.startswith("docling"):
        return "docling"
    return None


def _line_item_group_ids(
    document_id: str,
    items: list[RegionLineItem],
) -> list[str | None]:
    """Assign deterministic line-item group IDs with sibling awareness.

    A structural anchor identifies a row only when it is row-scoped: it carries
    a row_index, or no sibling line item shares the same anchor. Region-level
    anchors stamped onto every row (null row_index) fall back to the row's own
    content plus occurrence index so distinct rows never collapse into one
    group and identical repeated rows survive as separate rows.
    """
    anchors = [claim_anchor_from_evidence(item.evidence) for item in items]
    anchor_keys = [
        _stable_json(anchor.identity_json()) if anchor is not None else None for anchor in anchors
    ]
    shared_counts: dict[str, int] = {}
    for key in anchor_keys:
        if key is not None:
            shared_counts[key] = shared_counts.get(key, 0) + 1
    group_ids: list[str | None] = []
    occurrences: dict[str, int] = {}
    for item, anchor, key in zip(items, anchors, anchor_keys, strict=True):
        if anchor is None or key is None:
            group_ids.append(None)
            continue
        if anchor.row_index is not None or shared_counts[key] == 1:
            group_ids.append(
                _sha256(
                    {
                        "document_id": document_id,
                        "anchor": anchor.identity_json(),
                    }
                )
            )
            continue
        content = _line_item_content_fingerprint(item)
        occurrence_key = f"{key}|{content}"
        occurrences[occurrence_key] = occurrences.get(occurrence_key, 0) + 1
        group_ids.append(
            _sha256(
                {
                    "document_id": document_id,
                    "anchor": anchor.identity_json(),
                    "content": content,
                    "occurrence": occurrences[occurrence_key],
                }
            )
        )
    return group_ids


def _line_item_content_fingerprint(item: RegionLineItem) -> str:
    payload = item.model_dump(
        mode="json",
        exclude={"evidence", "confidence", "source_payload", "ordinal"},
        exclude_none=True,
    )
    return _sha256(payload)


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
            "anchor": anchor.identity_json(),
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
