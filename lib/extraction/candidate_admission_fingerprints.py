from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any
from uuid import UUID

from lib.extraction.candidate_admission_models import CandidateAdmissionContext, CandidateKind
from lib.extraction.models import CandidateFact, LineItemCandidateFact, ObservationCandidateFact


def field_fingerprint(candidate: CandidateFact, context: CandidateAdmissionContext) -> str:
    return _fingerprint(
        {
            "kind": "field",
            "field_path": _normalized_text(candidate.field_path),
            "value": _normalized_json_value(candidate.value),
            "region": _region_key(context, candidate.evidence),
        }
    )


def line_item_fingerprint(
    candidate: LineItemCandidateFact,
    context: CandidateAdmissionContext,
) -> str:
    return _fingerprint(
        {
            "kind": "line_item",
            "description": _normalized_text(candidate.description),
            "code": _normalized_text(candidate.code),
            "quantity": _float_key(candidate.quantity),
            "unit_price": _float_key(candidate.unit_price),
            "gross_amount": _float_key(candidate.gross_amount),
            "net_amount": _float_key(candidate.net_amount),
            "currency": _normalized_text(candidate.currency),
            "region": _region_key(context, candidate.evidence),
            "table": _table_key(candidate.evidence),
        }
    )


def observation_fingerprint(
    candidate: ObservationCandidateFact,
    context: CandidateAdmissionContext,
) -> str:
    return _fingerprint(
        {
            "kind": "observation",
            "family": _normalized_text(candidate.observation_family),
            "semantic_type": _normalized_text(
                candidate.metadata.get("semantic_type") or context.semantic_type
            ),
            "field_name": _normalized_text(candidate.field_name),
            "value": _normalized_json_value(candidate.value),
            "region": _region_key(context, candidate.evidence),
        }
    )


def raw_payload_fingerprint(
    *,
    candidate_kind: CandidateKind,
    field_path: str | None,
    payload: dict[str, Any],
    context: CandidateAdmissionContext,
) -> str:
    if candidate_kind == "line_item":
        fingerprint_payload = {
            "kind": "line_item",
            "description": _normalized_text(
                payload.get("description") or payload.get("service_description")
            ),
            "code": _normalized_text(
                payload.get("code") or payload.get("procedure_code") or payload.get("sku")
            ),
            "quantity": _float_key(_number_value(payload.get("quantity"))),
            "unit_price": _money_key(payload.get("unit_price")),
            "gross_amount": _money_key(payload.get("gross_amount") or payload.get("amount")),
            "net_amount": _money_key(payload.get("net_amount") or payload.get("amount")),
            "currency": _normalized_text(payload.get("currency") or payload.get("currency_code")),
            "region": _region_key(context, _evidence(payload)),
            "table": _table_key(_evidence(payload)),
        }
    elif candidate_kind == "observation":
        fingerprint_payload = {
            "kind": "observation",
            "family": _normalized_text(payload.get("family") or payload.get("observation_family")),
            "semantic_type": _normalized_text(
                payload.get("semantic_type") or context.semantic_type
            ),
            "field_name": _normalized_text(field_path or payload.get("field_name")),
            "value": _normalized_json_value(payload.get("value")),
            "region": _region_key(context, _evidence(payload)),
        }
    else:
        fingerprint_payload = {
            "kind": "field",
            "field_path": _normalized_text(field_path or payload.get("field_path")),
            "value": _normalized_json_value(payload.get("value")),
            "region": _region_key(context, _evidence(payload)),
        }
    return _fingerprint(fingerprint_payload)


def _region_key(
    context: CandidateAdmissionContext,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    first = evidence[0] if evidence else {}
    return {
        "semantic_region_id": str(
            first.get("semantic_region_id") or context.semantic_region_id or ""
        ),
        "page_number": first.get("page_number"),
        "page_id": str(first.get("page_id") or ""),
        "element_id": str(first.get("element_id") or ""),
        "table_id": str(first.get("table_id") or ""),
        "row_index": first.get("row_index"),
    }


def _table_key(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    first = evidence[0] if evidence else {}
    return {
        "table_id": str(first.get("table_id") or ""),
        "row_index": first.get("row_index"),
    }


def _money_key(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("amount")
    return _number_value(value)


def _number_value(value: Any) -> float | None:
    if isinstance(value, int | float):
        return _float_key(float(value))
    return None


def _float_key(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _evidence(owner: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = owner.get("evidence")
    return evidence if isinstance(evidence, list) else []


def _normalized_text(value: object) -> str:
    if value in (None, ""):
        return ""
    return " ".join(str(value).strip().lower().split())


def _normalized_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return _normalized_text(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): _normalized_json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple, set)):
        return [_normalized_json_value(item) for item in value]
    return value


def _fingerprint(payload: dict[str, Any]) -> str:
    serialized = json.dumps(
        _normalized_json_value(payload),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
