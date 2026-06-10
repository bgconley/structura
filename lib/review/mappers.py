from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from lib.contracts import (
    CanonicalField,
    FieldCandidate,
    LineItemCandidate,
    ObservationCandidate,
    ReviewTask,
)
from lib.extraction.candidate_repository import value_from_candidate_row
from lib.model_runtime.source_engines import (
    is_model_source_engine,
    is_qwen_source_engine,
    normalize_source_engine,
)

_CONTRACT_SOURCE_ENGINES = frozenset(
    {
        "docling",
        "qwen3_vl_2b",
        "qwen3_vl_4b",
        "qwen3_vl_8b",
        "granite_vision_3b",
        "validator",
        "human",
        "system",
    }
)


def review_task_from_row(row: Mapping[str, Any]) -> ReviewTask:
    metadata = row.get("metadata_json") or {}
    return ReviewTask.model_validate(
        {
            "id": row["id"],
            "documentId": row["document_id"],
            "taskType": row["task_type"],
            "status": row["status"],
            "priority": row["priority"],
            "pageNumber": metadata.get("pageNumber"),
            "fieldPath": metadata.get("fieldPath"),
            "rationale": row.get("reason"),
            "metadata": metadata if isinstance(metadata, dict) else None,
        }
    )


def field_candidate_from_row(row: Mapping[str, Any]) -> FieldCandidate:
    return FieldCandidate.model_validate(
        {
            "id": row["id"],
            "documentId": row["document_id"],
            "extractionId": row.get("extraction_id"),
            "fieldPath": row["field_path"],
            "ordinal": row["ordinal"],
            "valueType": row["value_type"],
            "value": value_from_candidate_row(row),
            "normalizedValue": value_from_candidate_row(row),
            "currency": row.get("currency_code"),
            "confidence": row.get("confidence"),
            "authorityWeight": row.get("authority_weight"),
            "sourceEngine": row["source_engine"],
            "evidence": evidence_refs_from_json(row.get("evidence_json"))
            or (row.get("evidence_json") or []),
            "validation": row.get("validation_json") or {},
            "status": row.get("status"),
        }
    )


def observation_candidate_from_row(row: Mapping[str, Any]) -> ObservationCandidate:
    return ObservationCandidate.model_validate(
        {
            "id": row["id"],
            "documentId": row["document_id"],
            "extractionId": row.get("extraction_id"),
            "observationFamily": row.get("observation_family"),
            "fieldName": row["field_name"],
            "valueType": row.get("value_type") or "string",
            "value": row.get("value_json"),
            "confidence": row.get("confidence"),
            "sourceEngine": row["source_engine"],
            "semanticType": row.get("semantic_type"),
            "modelOutputSchemaName": row.get("model_output_schema_name"),
            "evidence": evidence_refs_from_json(row.get("evidence_json")),
            "validation": row.get("validation_json") or {},
            "status": row.get("status"),
        }
    )


def line_item_candidate_from_row(row: Mapping[str, Any]) -> LineItemCandidate:
    return LineItemCandidate.model_validate(
        {
            "id": row["id"],
            "documentId": row["document_id"],
            "extractionId": row.get("extraction_id"),
            "lineItemType": row["line_item_type"],
            "ordinal": row["ordinal"],
            "code": row.get("code"),
            "serviceDate": row.get("service_date"),
            "description": row.get("description"),
            "quantity": _float_or_none(row.get("quantity")),
            "unit": row.get("unit"),
            "unitPrice": _float_or_none(row.get("unit_price")),
            "netAmount": _float_or_none(row.get("net_amount")),
            "currency": row.get("currency_code"),
            "categoryHint": row.get("category_hint"),
            "confidence": row.get("confidence"),
            "sourceEngine": row["source_engine"],
            "evidence": evidence_refs_from_json(row.get("evidence_json")),
            "validation": row.get("validation_json") or {},
            "status": row.get("status"),
        }
    )


def canonical_field_from_row(row: Mapping[str, Any]) -> CanonicalField:
    return CanonicalField.model_validate(
        {
            "id": row["id"],
            "documentId": row["document_id"],
            "selectedCandidateId": row.get("selected_candidate_id"),
            "fieldPath": row["field_path"],
            "ordinal": row["ordinal"],
            "valueType": row["value_type"],
            "value": canonical_value(row),
            "currency": row.get("currency_code"),
            "sourceKind": row["source_kind"],
            "reviewStatus": row["review_status"],
            "evidence": row.get("evidence_json") or [],
            "validation": row.get("validation_json") or {},
            "acceptedAt": row.get("accepted_at"),
        }
    )


def canonical_value(row: Mapping[str, Any] | None) -> Any:
    if not row:
        return None
    return value_from_candidate_row(row)


def evidence_refs_from_json(evidence: object) -> list[dict[str, Any]]:
    """Project stored evidence JSON into contract `EvidenceRef` payloads.

    Stored candidate evidence carries extended lineage keys (document ids,
    semantic annotation/region ids, page ids) that the API contract does not
    expose. Only contract locator keys are projected, and refs without a page
    number cannot be expressed as contract evidence.
    """
    if not isinstance(evidence, list):
        return []
    refs: list[dict[str, Any]] = []
    for item in evidence:
        if not isinstance(item, Mapping):
            continue
        ref = _evidence_ref_payload(item)
        if ref is not None:
            refs.append(ref)
    return refs


def _evidence_ref_payload(item: Mapping[str, Any]) -> dict[str, Any] | None:
    page_number = _evidence_value(item, "page_number", "pageNumber")
    if not isinstance(page_number, int) or page_number < 1:
        return None
    payload: dict[str, Any] = {
        "pageNumber": page_number,
        "sourceEngine": _contract_source_engine(
            _evidence_value(item, "source_engine", "sourceEngine")
        ),
    }
    bbox = item.get("bbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        payload["bbox"] = [float(value) for value in bbox]
    element_id = _uuid_or_none(_evidence_value(item, "element_id", "elementId"))
    if element_id is not None:
        payload["elementId"] = element_id
    table_id = _uuid_or_none(_evidence_value(item, "table_id", "tableId"))
    if table_id is not None:
        payload["tableId"] = table_id
    row_index = _evidence_value(item, "row_index", "rowIndex")
    if isinstance(row_index, int) and row_index >= 0:
        payload["rowIndex"] = row_index
    column_index = _evidence_value(item, "column_index", "columnIndex")
    if isinstance(column_index, int) and column_index >= 0:
        payload["columnIndex"] = column_index
    source_text = _evidence_value(item, "source_text", "sourceText")
    if isinstance(source_text, str) and source_text:
        payload["sourceText"] = source_text
    text_span = _text_span_payload(_evidence_value(item, "text_span", "textSpan"))
    if text_span is not None:
        payload["textSpan"] = text_span
    confidence = item.get("confidence")
    if isinstance(confidence, (int, float)):
        payload["confidence"] = float(confidence)
    if not _has_contract_locator(payload):
        return None
    return payload


def _text_span_payload(value: object) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    start = value.get("start")
    end = value.get("end")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < 0:
        return None
    payload: dict[str, Any] = {"start": start, "end": end}
    basis = value.get("basis")
    if basis in ("page_text", "chunk_text", "element_text", "raw_model_output"):
        payload["basis"] = basis
    return payload


def _has_contract_locator(payload: Mapping[str, Any]) -> bool:
    return any(
        (
            payload.get("bbox") is not None,
            payload.get("elementId") is not None,
            payload.get("tableId") is not None and payload.get("rowIndex") is not None,
            payload.get("textSpan") is not None,
            payload.get("sourceText") is not None,
        )
    )


def _contract_source_engine(value: object) -> str:
    normalized = normalize_source_engine(value)
    if normalized in _CONTRACT_SOURCE_ENGINES:
        return normalized
    if is_qwen_source_engine(normalized):
        return "qwen3_vl_8b"
    if is_model_source_engine(normalized):
        return "granite_vision_3b"
    if normalized.startswith("docling"):
        return "docling"
    return "system"


def _evidence_value(item: Mapping[str, Any], snake_key: str, camel_key: str) -> Any:
    value = item.get(snake_key)
    if value is None:
        value = item.get(camel_key)
    return value


def _uuid_or_none(value: object) -> str | None:
    if value in (None, ""):
        return None
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
