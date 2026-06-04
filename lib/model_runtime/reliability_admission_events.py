from __future__ import annotations

from typing import Any

from lib.candidate_quality_policy import (
    contains_placeholder_value,
    contains_prompt_or_schema_artifact,
)
from lib.model_runtime.reliability_report_normalization import (
    all_rows,
    bool_value,
    dict_value,
    get_value,
)
from lib.model_runtime.reliability_versions import (
    CANDIDATE_GATE_VERSION,
    CONTRACT_REGISTRY_VERSION,
    PLANNER_VERSION,
    REGION_ENVELOPE_VERSION,
)
from lib.model_runtime.source_engines import is_model_source_engine

ViolationMap = dict[str, list[dict[str, Any]]]


def evaluate_admission_events(documents: list[dict[str, Any]], violations: ViolationMap) -> None:
    for event in all_rows(documents, "admissionEvents"):
        _evaluate_event_telemetry(event, violations)
        if not _is_admitted(event):
            continue
        candidate = _candidate_payload(event)
        if _contains_prompt_or_schema_artifact(candidate):
            _add_violation(
                violations,
                "promptSchemaArtifactsAdmitted",
                event,
                "admitted_prompt_or_schema_artifact",
            )
        if contains_placeholder_value(candidate):
            _add_violation(
                violations,
                "placeholderOrLiteralNullCandidatesAdmitted",
                event,
                "admitted_placeholder_or_literal_null",
            )
        if not bool_value(get_value(event, "evidence_concrete", "evidenceConcrete")):
            _add_violation(
                violations,
                "admittedCandidatesWithoutConcreteEvidence",
                event,
                "admitted_without_concrete_evidence",
            )


def _evaluate_event_telemetry(event: dict[str, Any], violations: ViolationMap) -> None:
    for snake_key, camel_key, reason in (
        ("run_id", "runId", "missing_run_id"),
        ("planner_version", "plannerVersion", "missing_planner_version"),
        ("candidate_fingerprint", "candidateFingerprint", "missing_candidate_fingerprint"),
        ("candidate_gate_version", "candidateGateVersion", "missing_candidate_gate_version"),
        (
            "contract_registry_version",
            "contractRegistryVersion",
            "missing_contract_registry_version",
        ),
    ):
        if not _has_text(get_value(event, snake_key, camel_key)):
            _add_violation(violations, "admissionEventsMissingTelemetry", event, reason)

    for snake_key, camel_key, expected, reason in (
        ("planner_version", "plannerVersion", PLANNER_VERSION, "stale_planner_version"),
        (
            "candidate_gate_version",
            "candidateGateVersion",
            CANDIDATE_GATE_VERSION,
            "stale_candidate_gate_version",
        ),
        (
            "contract_registry_version",
            "contractRegistryVersion",
            CONTRACT_REGISTRY_VERSION,
            "stale_contract_registry_version",
        ),
    ):
        _evaluate_expected_version(
            event,
            violations,
            snake_key=snake_key,
            camel_key=camel_key,
            expected=expected,
            reason=reason,
        )

    if _is_model_backed_event(event):
        for snake_key, camel_key, reason in (
            ("plan_id", "planId", "missing_plan_id"),
            ("plan_task_id", "planTaskId", "missing_plan_task_id"),
            (
                "semantic_annotation_id",
                "semanticAnnotationId",
                "missing_semantic_annotation_id",
            ),
            (
                "region_envelope_version",
                "regionEnvelopeVersion",
                "missing_region_envelope_version",
            ),
        ):
            if not _has_value(get_value(event, snake_key, camel_key)):
                _add_violation(violations, "admissionEventsMissingTelemetry", event, reason)
        _evaluate_expected_version(
            event,
            violations,
            snake_key="region_envelope_version",
            camel_key="regionEnvelopeVersion",
            expected=REGION_ENVELOPE_VERSION,
            reason="stale_region_envelope_version",
        )


def _is_admitted(event: dict[str, Any]) -> bool:
    return _normalized_decision(get_value(event, "decision")).startswith("admitted")


def _is_model_backed_event(event: dict[str, Any]) -> bool:
    source_engine = get_value(event, "source_engine", "sourceEngine")
    if is_model_source_engine(source_engine):
        return True
    return get_value(event, "semantic_region_id", "semanticRegionId") not in (None, "")


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _has_value(value: Any) -> bool:
    if value in (None, ""):
        return False
    return not (isinstance(value, str) and not value.strip())


def _evaluate_expected_version(
    event: dict[str, Any],
    violations: ViolationMap,
    *,
    snake_key: str,
    camel_key: str,
    expected: str,
    reason: str,
) -> None:
    value = get_value(event, snake_key, camel_key)
    if value in (None, ""):
        return
    if str(value).strip() != expected:
        _add_violation(violations, "admissionEventsMissingTelemetry", event, reason)


def _candidate_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = dict_value(get_value(event, "payload_json", "payloadJson"))
    candidate = dict_value(get_value(payload, "candidate"))
    return candidate or payload


def _contains_prompt_or_schema_artifact(candidate: dict[str, Any]) -> bool:
    return contains_prompt_or_schema_artifact(candidate)


def _normalized_decision(value: Any) -> str:
    return str(value or "").strip().lower()


def _add_violation(
    violations: ViolationMap,
    key: str,
    row: dict[str, Any],
    reason: str,
) -> None:
    violations[key].append(
        {
            "reason": reason,
            "documentId": get_value(row, "document_id", "documentId"),
            "entityId": _first_non_empty(
                get_value(row, "id"),
                get_value(row, "candidate_fingerprint", "candidateFingerprint"),
                get_value(row, "field_path", "fieldPath"),
                get_value(row, "candidate_kind", "candidateKind"),
            ),
        }
    )


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None
