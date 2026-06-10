from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lib.extraction.evidence import is_concrete_evidence_ref

ANALYSIS_TARGET_JOB_QUEUES = {
    "docling",
    "semantic-annotations",
    "extraction",
    "visual-embeddings",
}
OPERATIONAL_FAILURE_STATUSES = {"failed", "dead_letter", "pipeline_failed"}
TERMINAL_JOB_FAILURE_STATUSES = {"dead_letter", "pipeline_failed"}
QUALITY_OUTCOME_STATUSES = {
    "extracted_cleanly",
    "needs_human_review",
    "insufficient_signal",
    "no_extraction_target",
}
ADMITTED_ARTIFACT_REASONS = {
    "fake_schema_line_item",
    "missing_description",
    "placeholder_field_name",
    "placeholder_or_null_value",
    "prompt_or_schema_echo",
}


def phase9_document_eligibility(document_quality: Mapping[str, Any]) -> str:
    if _value(document_quality, "operational_status", "operationalStatus") != "completed":
        return "analysis_disabled_operational_failure"
    if (
        _int(_value(document_quality, "canonical_fact_count", "canonicalFactCount")) == 0
        and _int(_value(document_quality, "candidate_count", "candidateCount")) == 0
    ):
        return "analysis_limited_no_extracted_facts"
    evidence_coverage = _float(
        _value(document_quality, "evidence_locator_coverage", "evidenceLocatorCoverage")
    )
    if evidence_coverage < 0.80:
        return "analysis_review_only_evidence_sparse"
    if bool(_value(document_quality, "has_admitted_artifact", "hasAdmittedArtifact")):
        return "analysis_disabled_artifact_regression"
    return "analysis_enabled_with_uncertainty"


def build_document_quality(
    document: Mapping[str, Any],
    *,
    truth: Mapping[str, list[Mapping[str, Any]]],
    review: Mapping[str, Any],
) -> dict[str, Any]:
    explicit = _mapping(_value(document, "documentQuality", "document_quality"))
    quality_outcome = _quality_outcome(explicit)
    operational_status = _explicit_operational_status(explicit) or _operational_status(document)
    canonical_count = sum(
        len(truth.get(key, []))
        for key in (
            "canonicalFields",
            "canonicalLineItems",
            "canonicalObservations",
            "userConfirmedFacts",
        )
    )
    candidate_count = sum(
        len(review.get(key, []))
        for key in ("fieldCandidates", "lineItemCandidates", "observationCandidates")
    )
    quality = {
        "operational_status": operational_status,
        "canonical_fact_count": _value(explicit, "canonical_fact_count", "canonicalFactCount")
        if _value(explicit, "canonical_fact_count", "canonicalFactCount") is not None
        else canonical_count,
        "candidate_count": _value(explicit, "candidate_count", "candidateCount")
        if _value(explicit, "candidate_count", "candidateCount") is not None
        else candidate_count,
        "evidence_locator_coverage": _value(
            explicit,
            "evidence_locator_coverage",
            "evidenceLocatorCoverage",
        )
        if _value(explicit, "evidence_locator_coverage", "evidenceLocatorCoverage") is not None
        else _evidence_locator_coverage([truth, review]),
        "has_admitted_artifact": _value(
            explicit,
            "has_admitted_artifact",
            "hasAdmittedArtifact",
        )
        if _value(explicit, "has_admitted_artifact", "hasAdmittedArtifact") is not None
        else _has_admitted_artifact(document),
    }
    if quality_outcome is not None:
        quality["quality_outcome"] = quality_outcome
    return quality


def _quality_outcome(explicit: Mapping[str, Any]) -> str | None:
    for key in (
        "quality_outcome",
        "qualityOutcome",
        "outcome",
        "quality_status",
        "qualityStatus",
        "operational_status",
        "operationalStatus",
    ):
        value = _normalized_status(_value(explicit, key))
        if value in QUALITY_OUTCOME_STATUSES:
            return value
    return None


def _explicit_operational_status(explicit: Mapping[str, Any]) -> str | None:
    value = _normalized_status(_value(explicit, "operational_status", "operationalStatus"))
    if value in QUALITY_OUTCOME_STATUSES:
        return None
    return value or None


def _operational_status(document: Mapping[str, Any]) -> str:
    extraction_statuses = {
        str(_value(row, "status") or "").lower()
        for row in [*_rows(document, "extractions"), *_rows(document, "semanticRegionExtractions")]
    }
    if any(status in OPERATIONAL_FAILURE_STATUSES for status in extraction_statuses):
        return "pipeline_failed"
    for job in _rows(document, "jobs"):
        queue_name = str(_value(job, "queueName", "queue_name", "queue") or "").lower()
        if queue_name in ANALYSIS_TARGET_JOB_QUEUES and _job_failure_is_terminal(job):
            return "pipeline_failed"
    return "completed"


def _job_failure_is_terminal(job: Mapping[str, Any]) -> bool:
    status = str(_value(job, "status") or "").lower()
    if status in TERMINAL_JOB_FAILURE_STATUSES:
        return True
    if status != "failed":
        return False
    # fail_job keeps retryable jobs in status 'failed' between attempts; a
    # pending retry is pipeline in-progress, not the terminal pipeline_failed
    # quality outcome ADR D8 reserves for runtime defects.
    error_json = _mapping(_value(job, "errorJson", "error_json"))
    if error_json.get("retryable") is False:
        return True
    attempts = _value(job, "attemptCount", "attempt_count", "attempts")
    max_attempts = _value(job, "maxAttempts", "max_attempts")
    if attempts is not None and max_attempts is not None:
        return _int(attempts) >= _int(max_attempts)
    return False


def _has_admitted_artifact(document: Mapping[str, Any]) -> bool:
    for event in _rows(document, "admissionEvents", "candidateAdmissionEvents"):
        decision = str(_value(event, "decision") or "")
        reasons = [str(reason) for reason in _list(_value(event, "reasons"))]
        if decision.startswith("admitted") and any(
            reason in ADMITTED_ARTIFACT_REASONS for reason in reasons
        ):
            return True
    return False


def _evidence_locator_coverage(containers: list[Any]) -> float:
    evidence_refs = _collect_evidence(containers)
    if not evidence_refs:
        return 1.0
    concrete = sum(1 for evidence in evidence_refs if _has_concrete_locator(evidence))
    return round(concrete / len(evidence_refs), 4)


def _collect_evidence(value: Any) -> list[Any]:
    if isinstance(value, Mapping):
        evidence = _value(value, "evidence", "evidenceRefs")
        evidence_refs = list(_list(evidence))
        for item in value.values():
            evidence_refs.extend(_collect_evidence(item))
        return evidence_refs
    if isinstance(value, list):
        refs: list[Any] = []
        for item in value:
            refs.extend(_collect_evidence(item))
        return refs
    return []


def _has_concrete_locator(evidence: Any) -> bool:
    if not isinstance(evidence, Mapping):
        return False
    return is_concrete_evidence_ref(dict(evidence))


def _rows(mapping: Mapping[str, Any], *keys: str) -> list[Mapping[str, Any]]:
    for key in keys:
        value = _value(mapping, key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    return []


def _value(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(value)


def _float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _normalized_status(value: Any) -> str:
    return str(value or "").strip().lower()
