from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_report_normalization import dict_value, get_value, list_value

ViolationMap = dict[str, list[dict[str, Any]]]

__all__ = ["evaluate_rejected_candidate_insertions"]


def evaluate_rejected_candidate_insertions(
    documents: list[dict[str, Any]],
    violations: ViolationMap,
) -> None:
    for doc in documents:
        rejected = _rejected_candidate_identities(doc)
        if not rejected:
            continue
        document = dict_value(get_value(doc, "document"))
        for row in _inserted_candidate_rows(doc):
            identities = _candidate_row_identities(row)
            if rejected.isdisjoint(identities):
                continue
            _add_violation(
                violations,
                row,
                document=document,
            )


def _rejected_candidate_identities(doc: dict[str, Any]) -> set[str]:
    identities: set[str] = set()
    for event in list_value(get_value(doc, "admissionEvents", "candidateAdmissionEvents")):
        if not isinstance(event, dict):
            continue
        decision = str(get_value(event, "decision") or "")
        if not decision.startswith("rejected"):
            continue
        candidate_kind = str(get_value(event, "candidate_kind", "candidateKind") or "field")
        field_path = str(get_value(event, "field_path", "fieldPath") or "")
        fingerprint = get_value(event, "candidate_fingerprint", "candidateFingerprint")
        if fingerprint not in (None, ""):
            identities.add(f"fingerprint:{fingerprint}")
        identities.update(
            _candidate_payload_identities(
                candidate_kind=candidate_kind,
                field_path=field_path,
                payload=_candidate_payload(event),
            )
        )
    return identities


def _candidate_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = dict_value(get_value(event, "payload_json", "payloadJson"))
    candidate = dict_value(get_value(payload, "candidate"))
    return candidate or payload


def _inserted_candidate_rows(doc: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in (
        "fields",
        "canonicalFields",
        "canonical_fields",
        "fieldCandidates",
        "lineItems",
        "canonicalLineItems",
        "canonical_line_items",
        "lineItemCandidates",
        "observations",
        "canonicalObservations",
        "canonical_observations",
        "observationCandidates",
    ):
        rows.extend(row for row in list_value(get_value(doc, key)) if isinstance(row, dict))
    return rows


def _candidate_row_identities(row: dict[str, Any]) -> set[str]:
    fingerprint = get_value(row, "candidate_fingerprint", "candidateFingerprint")
    identities = {f"fingerprint:{fingerprint}"} if fingerprint not in (None, "") else set()
    if get_value(row, "field_path", "fieldPath") not in (None, ""):
        identities.add(_field_identity(row))
    elif get_value(row, "observation_family", "observationFamily", "family") not in (None, ""):
        identities.add(_observation_identity(row))
    else:
        identities.add(_line_item_identity(row))
    return identities


def _candidate_payload_identities(
    *,
    candidate_kind: str,
    field_path: str,
    payload: dict[str, Any],
) -> set[str]:
    normalized_kind = candidate_kind.lower()
    if normalized_kind == "line_item":
        return {_line_item_identity(payload)}
    if normalized_kind == "observation":
        return {_observation_identity({**payload, "field_path": field_path})}
    return {_field_identity({**payload, "field_path": field_path or payload.get("field_path")})}


def _field_identity(row: dict[str, Any]) -> str:
    field_path = _normalized_identity_text(get_value(row, "field_path", "fieldPath"))
    value = get_value(row, "value")
    return f"field:{field_path}:{_identity_value(value)}"


def _line_item_identity(row: dict[str, Any]) -> str:
    description = _normalized_identity_text(
        get_value(row, "description", "service_description", "serviceDescription")
    )
    code = _normalized_identity_text(get_value(row, "code", "procedure_code", "procedureCode"))
    net_amount = get_value(row, "net_amount", "netAmount", "amount")
    gross_amount = get_value(row, "gross_amount", "grossAmount", "amount")
    return (
        f"line_item:{description}:{code}:"
        f"{_identity_value(net_amount)}:{_identity_value(gross_amount)}"
    )


def _observation_identity(row: dict[str, Any]) -> str:
    family = _normalized_identity_text(
        get_value(row, "observation_family", "observationFamily", "family")
    )
    field_name = _normalized_identity_text(
        get_value(row, "field_name", "fieldName", "field_path", "fieldPath")
    )
    value = get_value(row, "value", "value_json", "valueJson")
    return f"observation:{family}:{field_name}:{_identity_value(value)}"


def _identity_value(value: Any) -> str:
    if isinstance(value, dict):
        return "|".join(
            f"{_normalized_identity_text(key)}={_identity_value(item)}"
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    if isinstance(value, list | tuple):
        return "[" + ",".join(_identity_value(item) for item in value) + "]"
    return _normalized_identity_text(value)


def _normalized_identity_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    return " ".join(str(value).strip().lower().split())


def _add_violation(
    violations: ViolationMap,
    row: dict[str, Any],
    *,
    document: dict[str, Any],
) -> None:
    source = document or row
    violations["rejectedCandidatesInserted"].append(
        {
            "reason": "rejected_candidate_inserted",
            "documentId": get_value(source, "document_id", "documentId", "id"),
            "entityId": get_value(row, "id", "candidate_id", "candidateId"),
        }
    )
