from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_report_normalization import (
    dict_value,
    get_value,
    list_value,
    snake,
)

ViolationMap = dict[str, list[dict[str, Any]]]
IdentitySet = tuple[set[str], set[str]]

__all__ = ["evaluate_rejected_candidate_insertions"]


def evaluate_rejected_candidate_insertions(
    documents: list[dict[str, Any]],
    violations: ViolationMap,
) -> None:
    for doc in documents:
        rejected = _rejected_candidate_identities(doc)
        if not rejected[0] and not rejected[1]:
            continue
        document = dict_value(get_value(doc, "document"))
        for row in _inserted_candidate_rows(doc):
            identities = _candidate_row_identities(row)
            if not _identity_sets_intersect(rejected, identities):
                continue
            _add_violation(
                violations,
                row,
                document=document,
            )


def _rejected_candidate_identities(doc: dict[str, Any]) -> IdentitySet:
    fingerprints: set[str] = set()
    fallbacks: set[str] = set()
    for event in list_value(get_value(doc, "admissionEvents", "candidateAdmissionEvents")):
        if not isinstance(event, dict):
            continue
        decision = _normalized_decision(get_value(event, "decision"))
        if not decision.startswith("rejected"):
            continue
        candidate_kind = str(get_value(event, "candidate_kind", "candidateKind") or "field")
        field_path = str(get_value(event, "field_path", "fieldPath") or "")
        fingerprint = get_value(event, "candidate_fingerprint", "candidateFingerprint")
        if fingerprint not in (None, ""):
            fingerprints.add(_fingerprint_identity(candidate_kind, fingerprint))
        fallbacks.update(
            _candidate_payload_identities(
                candidate_kind=candidate_kind,
                field_path=field_path,
                event=event,
                payload=_candidate_payload(event),
            )
        )
    return fingerprints, fallbacks


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


def _candidate_row_identities(row: dict[str, Any]) -> IdentitySet:
    candidate_kind = _candidate_row_kind(row)
    fingerprint = get_value(row, "candidate_fingerprint", "candidateFingerprint")
    fingerprints = (
        {_fingerprint_identity(candidate_kind, fingerprint)}
        if fingerprint not in (None, "")
        else set()
    )
    return fingerprints, _candidate_fallback_identities(candidate_kind, row)


def _candidate_payload_identities(
    *,
    candidate_kind: str,
    field_path: str,
    event: dict[str, Any],
    payload: dict[str, Any],
) -> set[str]:
    normalized_kind = _normalized_candidate_kind(candidate_kind)
    row = {
        **payload,
        "field_path": field_path or payload.get("field_path"),
        "source_engine": get_value(event, "source_engine", "sourceEngine")
        or get_value(payload, "source_engine", "sourceEngine"),
        "extraction_scope": get_value(event, "extraction_scope", "extractionScope")
        or get_value(payload, "extraction_scope", "extractionScope"),
    }
    return _candidate_fallback_identities(normalized_kind, row)


def _candidate_fallback_identities(
    candidate_kind: str,
    row: dict[str, Any],
) -> set[str]:
    normalized_kind = _normalized_candidate_kind(candidate_kind)
    if normalized_kind == "line_item":
        return {_line_item_identity(row)}
    if normalized_kind == "observation":
        return {_observation_identity(row)}
    return {_field_identity(row)}


def _identity_sets_intersect(rejected: IdentitySet, inserted: IdentitySet) -> bool:
    rejected_fingerprints, rejected_fallbacks = rejected
    inserted_fingerprints, inserted_fallbacks = inserted
    if rejected_fingerprints and inserted_fingerprints:
        return not rejected_fingerprints.isdisjoint(inserted_fingerprints)
    return not rejected_fallbacks.isdisjoint(inserted_fallbacks)


def _fingerprint_identity(candidate_kind: Any, fingerprint: Any) -> str:
    return f"fingerprint:{_normalized_candidate_kind(candidate_kind)}:{fingerprint}"


def _candidate_row_kind(row: dict[str, Any]) -> str:
    explicit = get_value(row, "candidate_kind", "candidateKind")
    if explicit not in (None, ""):
        return str(explicit)
    if get_value(row, "field_path", "fieldPath") not in (None, ""):
        return "field"
    if get_value(row, "observation_family", "observationFamily", "family") not in (
        None,
        "",
    ):
        return "observation"
    return "line_item"


def _field_identity(row: dict[str, Any]) -> str:
    field_path = _normalized_identity_text(get_value(row, "field_path", "fieldPath"))
    value = get_value(row, "value")
    return _fallback_identity(
        candidate_kind="field",
        row=row,
        parts=(field_path, _identity_value(value)),
    )


def _line_item_identity(row: dict[str, Any]) -> str:
    description = _normalized_identity_text(
        get_value(row, "description", "service_description", "serviceDescription")
    )
    code = _normalized_identity_text(get_value(row, "code", "procedure_code", "procedureCode"))
    net_amount = get_value(row, "net_amount", "netAmount", "amount")
    gross_amount = get_value(row, "gross_amount", "grossAmount", "amount")
    return _fallback_identity(
        candidate_kind="line_item",
        row=row,
        parts=(
            description,
            code,
            _identity_value(net_amount),
            _identity_value(gross_amount),
        ),
    )


def _observation_identity(row: dict[str, Any]) -> str:
    family = _normalized_identity_text(
        get_value(row, "observation_family", "observationFamily", "family")
    )
    field_name = _normalized_identity_text(
        get_value(row, "field_name", "fieldName", "field_path", "fieldPath")
    )
    value = get_value(row, "value", "value_json", "valueJson")
    return _fallback_identity(
        candidate_kind="observation",
        row=row,
        parts=(family, field_name, _identity_value(value)),
    )


def _fallback_identity(
    *,
    candidate_kind: str,
    row: dict[str, Any],
    parts: tuple[str, ...],
) -> str:
    return ":".join(
        (
            candidate_kind,
            _normalized_identity_text(get_value(row, "source_engine", "sourceEngine")),
            _normalized_identity_text(get_value(row, "extraction_scope", "extractionScope")),
            _evidence_identity(row),
            *parts,
        )
    )


def _evidence_identity(row: dict[str, Any]) -> str:
    evidence_items = list_value(get_value(row, "evidence", "evidence_json", "evidenceJson"))
    locators = [_evidence_locator(item) for item in evidence_items if isinstance(item, dict)]
    return "|".join(sorted(locator for locator in locators if locator))


def _evidence_locator(evidence: dict[str, Any]) -> str:
    fields = (
        "page_id",
        "pageId",
        "page_number",
        "pageNumber",
        "semantic_region_id",
        "semanticRegionId",
        "table_id",
        "tableId",
        "row_index",
        "rowIndex",
        "element_id",
        "elementId",
        "text_span",
        "textSpan",
    )
    values = [
        _normalized_identity_text(get_value(evidence, field))
        for field in fields
        if get_value(evidence, field) not in (None, "")
    ]
    return ",".join(values)


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


def _normalized_candidate_kind(value: Any) -> str:
    normalized = snake(str(value or "").strip()).replace("-", "_").replace(" ", "_").lower()
    return "_".join(part for part in normalized.split("_") if part)


def _normalized_decision(value: Any) -> str:
    return str(value or "").strip().lower()


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
