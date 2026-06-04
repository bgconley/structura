from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

REGION_ENVELOPE_VERSION = "phase8_5-region-envelope-v1"
ValueType = Literal[
    "string",
    "number",
    "money",
    "date",
    "boolean",
    "object",
    "array",
    "null",
]


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    semantic_annotation_id: str | None = None
    semantic_region_id: str | None = None
    page_number: int | None = None
    page_id: str | None = None
    element_id: str | None = None
    table_id: str | None = None
    bbox: list[float] | None = None
    source_text: str | None = None
    source_engine: str
    confidence: float | None = None
    row_index: int | None = None
    text_span: dict[str, Any] | None = None
    visual_input_scope: str | None = None
    visual_input_sha256: str | None = None
    source_page_image_sha256: str | None = None
    bbox_basis: str | None = None
    original_bbox: list[float] | None = None
    expanded_bbox: list[float] | None = None
    rotation_policy: str | None = None
    crop_quality: dict[str, Any] | None = None
    visual_input_attempt: int | None = None


class RegionFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: Any
    value_type: ValueType
    confidence: float | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    source_text: str | None = None
    source_payload: dict[str, Any] = Field(default_factory=dict)


class RegionLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordinal: int | None = None
    line_item_type: str | None = None
    description: str | None = None
    code: str | None = None
    quantity: float | None = None
    unit: str | None = None
    unit_price: float | None = None
    gross_amount: float | None = None
    net_amount: float | None = None
    tax_amount: float | None = None
    currency_code: str | None = None
    service_date: str | None = None
    category_hint: str | None = None
    confidence: float | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    row_index: int | None = None
    table_id: str | None = None
    page_number: int | None = None
    source_payload: dict[str, Any] = Field(default_factory=dict)


class RegionTableRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_index: int | None = None
    row_type: str | None = None
    cells: dict[str, Any] = Field(default_factory=dict)
    normalized_fields: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    source_payload: dict[str, Any] = Field(default_factory=dict)


class RegionExtractionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    semantic_annotation_id: str | None = None
    semantic_region_id: str | None = None
    resolved_document_type: str
    semantic_type: str
    target_schema: str | None = None
    model_output_schema_name: str
    coverage: dict[str, Any] = Field(default_factory=dict)
    facts: list[RegionFact] = Field(default_factory=list)
    line_items: list[RegionLineItem] = Field(default_factory=list)
    table_rows: list[RegionTableRow] = Field(default_factory=list)
    observations: list[RegionFact] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    abstentions: list[str] = Field(default_factory=list)


def envelope_from_normalization_projection(
    *,
    projection: dict[str, Any],
    model_output_schema_name: str | None,
    semantic_type: str | None,
    target_schema: str | None,
    resolved_document_type: str | None,
    source_engine: str | None = None,
) -> RegionExtractionEnvelope:
    document_id = str(projection.get("document_id") or "")
    schema_name = str(projection.get("schema_name") or target_schema or "document_observation")
    envelope = RegionExtractionEnvelope(
        document_id=document_id,
        semantic_annotation_id=_first_context_value(projection, "semantic_annotation_id"),
        semantic_region_id=_first_context_value(projection, "semantic_region_id"),
        resolved_document_type=resolved_document_type or schema_name,
        semantic_type=semantic_type or "unknown",
        target_schema=target_schema or schema_name,
        model_output_schema_name=model_output_schema_name or "uncontracted_model_output",
        coverage={
            "schema_name": schema_name,
            "schema_version": projection.get("schema_version") or "v1",
            "confidence": deepcopy(projection.get("confidence") or {}),
            "metadata": deepcopy(projection.get("metadata") or {}),
            "created_at": projection.get("created_at"),
            "normalized_projection": deepcopy(projection),
        },
        facts=_facts_from_projection(
            projection,
            document_id=document_id,
            source_engine=source_engine,
        ),
        line_items=_line_items_from_projection(
            projection,
            document_id=document_id,
            source_engine=source_engine,
        ),
        observations=_observations_from_projection(
            projection,
            document_id=document_id,
            source_engine=source_engine,
        ),
        warnings=_string_list(projection.get("warnings")),
        abstentions=_string_list(projection.get("abstentions")),
    )
    return envelope


def to_normalization_projection(envelope: RegionExtractionEnvelope) -> dict[str, Any]:
    stored = envelope.coverage.get("normalized_projection")
    if isinstance(stored, dict):
        projection = deepcopy(stored)
    else:
        projection = _minimal_projection(envelope)
    projection["document_id"] = envelope.document_id
    projection.setdefault("schema_name", envelope.target_schema or envelope.resolved_document_type)
    projection.setdefault("schema_version", envelope.coverage.get("schema_version") or "v1")
    projection.setdefault("confidence", deepcopy(envelope.coverage.get("confidence") or {}))
    if envelope.coverage.get("metadata") and "metadata" not in projection:
        projection["metadata"] = deepcopy(envelope.coverage["metadata"])
    if envelope.coverage.get("created_at") and "created_at" not in projection:
        projection["created_at"] = envelope.coverage["created_at"]
    return projection


def region_envelope_from_normalization_json(
    normalization_json: dict[str, Any] | None,
) -> RegionExtractionEnvelope | None:
    if not isinstance(normalization_json, dict):
        return None
    payload = normalization_json.get("regionEnvelope")
    if not isinstance(payload, dict):
        return None
    return RegionExtractionEnvelope.model_validate(payload)


def envelope_json(envelope: RegionExtractionEnvelope) -> dict[str, Any]:
    return envelope.model_dump(mode="json", exclude_none=True)


def _facts_from_projection(
    projection: dict[str, Any],
    *,
    document_id: str,
    source_engine: str | None,
) -> list[RegionFact]:
    schema_name = str(projection.get("schema_name") or "")
    facts: list[RegionFact] = []
    if schema_name == "receipt":
        merchant = _dict_or_empty(projection.get("merchant"))
        if merchant.get("display_name") not in (None, ""):
            facts.append(
                _fact(
                    "receipt.merchant.display_name",
                    merchant["display_name"],
                    owner=merchant,
                    document_id=document_id,
                    source_engine=source_engine,
                )
            )
        transaction = _dict_or_empty(projection.get("transaction"))
        for key, value_type in (
            ("date_local", "date"),
            ("subtotal", "money"),
            ("tax", "money"),
            ("tip", "money"),
            ("total", "money"),
        ):
            if transaction.get(key) not in (None, ""):
                value_owner = _dict_or_empty(transaction.get(key)) or transaction
                facts.append(
                    _fact(
                        f"receipt.transaction.{key}",
                        transaction[key],
                        owner=value_owner,
                        value_type=cast(ValueType, value_type),
                        document_id=document_id,
                        source_engine=source_engine,
                    )
                )
    elif schema_name == "invoice":
        for container_name, fields in (
            ("seller", (("display_name", "invoice.seller.display_name", "string"),)),
            (
                "invoice",
                (
                    ("invoice_number", "invoice.invoice_number", "string"),
                    ("issued_on", "invoice.issue_date", "date"),
                    ("due_on", "invoice.due_date", "date"),
                ),
            ),
            (
                "totals",
                (
                    ("subtotal", "invoice.subtotal", "money"),
                    ("tax_total", "invoice.tax_total", "money"),
                    ("total", "invoice.total_amount", "money"),
                    ("balance_due", "invoice.balance_due", "money"),
                ),
            ),
        ):
            container = _dict_or_empty(projection.get(container_name))
            for key, name, value_type in fields:
                if container.get(key) not in (None, ""):
                    value_owner = _dict_or_empty(container.get(key)) or container
                    facts.append(
                        _fact(
                            name,
                            container[key],
                            owner=value_owner,
                            value_type=cast(ValueType, value_type),
                            document_id=document_id,
                            source_engine=source_engine,
                        )
                    )
    return facts


def _line_items_from_projection(
    projection: dict[str, Any],
    *,
    document_id: str,
    source_engine: str | None,
) -> list[RegionLineItem]:
    schema_name = str(projection.get("schema_name") or "")
    raw_items = (
        projection.get("service_lines")
        if schema_name == "medical_eob"
        else projection.get("line_items")
    )
    if not isinstance(raw_items, list):
        return []
    return [
        _line_item(
            item,
            schema_name=schema_name,
            document_id=document_id,
            source_engine=source_engine,
        )
        for item in raw_items
        if isinstance(item, dict)
    ]


def _observations_from_projection(
    projection: dict[str, Any],
    *,
    document_id: str,
    source_engine: str | None,
) -> list[RegionFact]:
    observations = projection.get("observations")
    if not isinstance(observations, list):
        return []
    facts: list[RegionFact] = []
    for item in observations:
        if not isinstance(item, dict) or item.get("field_name") in (None, ""):
            continue
        facts.append(
            _fact(
                str(item["field_name"]),
                item.get("value"),
                owner=item,
                value_type=_model_value_type(item.get("value_type"), item.get("value")),
                document_id=document_id,
                source_engine=source_engine,
            )
        )
    return facts


def _fact(
    name: str,
    value: Any,
    *,
    owner: dict[str, Any],
    document_id: str,
    source_engine: str | None,
    value_type: ValueType | None = None,
) -> RegionFact:
    return RegionFact(
        name=name,
        value=deepcopy(value),
        value_type=value_type or _value_type(value),
        confidence=_confidence(owner),
        evidence=_evidence_refs(
            owner.get("evidence"),
            document_id=document_id,
            source_engine=source_engine,
        ),
        source_text=_source_text(owner),
        source_payload=deepcopy(owner),
    )


def _line_item(
    item: dict[str, Any],
    *,
    schema_name: str,
    document_id: str,
    source_engine: str | None,
) -> RegionLineItem:
    amount = _dict_or_empty(item.get("amount"))
    unit_price = _dict_or_empty(item.get("unit_price"))
    return RegionLineItem(
        ordinal=_int_or_none(item.get("ordinal")),
        line_item_type="service_line" if schema_name == "medical_eob" else None,
        description=str(item.get("service_description") or item.get("description") or "") or None,
        code=item.get("procedure_code") or item.get("code") or item.get("sku"),
        quantity=_float_or_none(item.get("quantity")),
        unit=item.get("unit"),
        unit_price=_money_amount(item.get("unit_price")),
        gross_amount=_money_amount(item.get("billed_amount") or item.get("amount")),
        net_amount=_money_amount(item.get("patient_responsibility") or item.get("amount")),
        tax_amount=_money_amount(item.get("tax_amount")),
        currency_code=(
            item.get("currency_code")
            or amount.get("currency")
            or unit_price.get("currency")
            or _money_currency(item.get("patient_responsibility"))
        ),
        service_date=item.get("service_date"),
        category_hint=item.get("category_hint") or item.get("gl_hint"),
        confidence=_confidence(item),
        evidence=_evidence_refs(
            item.get("evidence"),
            document_id=document_id,
            source_engine=source_engine,
        ),
        row_index=_int_or_none(item.get("row_index")),
        table_id=str(item["table_id"]) if item.get("table_id") not in (None, "") else None,
        page_number=_int_or_none(item.get("page_number")),
        source_payload=deepcopy(item),
    )


def _minimal_projection(envelope: RegionExtractionEnvelope) -> dict[str, Any]:
    schema_name = envelope.target_schema or envelope.resolved_document_type
    projection: dict[str, Any] = {
        "schema_name": schema_name,
        "schema_version": envelope.coverage.get("schema_version") or "v1",
        "document_id": envelope.document_id,
        "confidence": deepcopy(envelope.coverage.get("confidence") or {}),
    }
    if schema_name == "document_observation":
        projection["observations"] = [
            fact.source_payload or _fact_payload(fact) for fact in envelope.observations
        ]
    else:
        projection["line_items"] = [
            item.source_payload or _line_item_payload(item) for item in envelope.line_items
        ]
    return projection


def _fact_payload(fact: RegionFact) -> dict[str, Any]:
    return {
        "field_name": fact.name,
        "value": fact.value,
        "value_type": fact.value_type,
        "confidence": fact.confidence,
        "evidence": [ref.model_dump(mode="json", exclude_none=True) for ref in fact.evidence],
    }


def _line_item_payload(item: RegionLineItem) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ordinal": item.ordinal,
        "description": item.description,
        "code": item.code,
        "quantity": item.quantity,
        "unit": item.unit,
        "service_date": item.service_date,
        "category_hint": item.category_hint,
        "evidence": [ref.model_dump(mode="json", exclude_none=True) for ref in item.evidence],
    }
    if item.net_amount is not None:
        payload["amount"] = {"amount": item.net_amount, "currency": item.currency_code}
    return {key: value for key, value in payload.items() if value not in (None, "")}


def _evidence_refs(
    evidence: Any,
    *,
    document_id: str,
    source_engine: str | None,
) -> list[EvidenceRef]:
    if not isinstance(evidence, list):
        return []
    refs: list[EvidenceRef] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        payload = deepcopy(item)
        payload.setdefault("document_id", document_id)
        payload.setdefault(
            "source_engine", source_engine or payload.get("source_engine") or "unknown"
        )
        refs.append(EvidenceRef.model_validate(payload))
    return refs


def _first_context_value(value: Any, key: str) -> str | None:
    if isinstance(value, dict):
        candidate = value.get(key)
        if candidate not in (None, ""):
            return str(candidate)
        for child in value.values():
            found = _first_context_value(child, key)
            if found:
                return found
    if isinstance(value, list):
        for child in value:
            found = _first_context_value(child, key)
            if found:
                return found
    return None


def _source_text(owner: dict[str, Any]) -> str | None:
    value = owner.get("source_text")
    if value not in (None, ""):
        return str(value)
    return None


def _confidence(owner: dict[str, Any]) -> float | None:
    value = owner.get("confidence")
    if isinstance(value, int | float):
        return float(value)
    return None


def _value_type(value: Any) -> ValueType:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, dict):
        if value.get("amount") is not None:
            return "money"
        return "object"
    if isinstance(value, list):
        return "array"
    return "string"


def _model_value_type(value_type: Any, value: Any) -> ValueType:
    normalized = str(value_type).strip().lower() if value_type not in (None, "") else ""
    if normalized == "json":
        return (
            "object"
            if isinstance(value, dict)
            else "array"
            if isinstance(value, list)
            else "string"
        )
    allowed = {"string", "number", "money", "date", "boolean", "object", "array", "null"}
    if normalized in allowed:
        return cast(ValueType, normalized)
    return _value_type(value)


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _money_amount(value: Any) -> float | None:
    if isinstance(value, dict) and value.get("amount") is not None:
        return _float_or_none(value["amount"])
    return _float_or_none(value)


def _money_currency(value: Any) -> str | None:
    if isinstance(value, dict) and value.get("currency") not in (None, ""):
        return str(value["currency"])
    return None


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item not in (None, "")]
