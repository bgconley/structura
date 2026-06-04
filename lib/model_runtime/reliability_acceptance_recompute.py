from __future__ import annotations

from collections import Counter
from typing import Any

from lib.model_runtime.reliability_fingerprints import repeatability_fingerprints
from lib.model_runtime.reliability_invariants import evaluate_hard_correctness_invariants
from lib.model_runtime.reliability_operational_slos import evaluate_operational_slos
from lib.model_runtime.reliability_report_normalization import (
    all_rows,
    bool_value,
    dict_value,
    first_report_value,
    get_value,
    int_value,
    list_value,
    sum_values,
)

__all__ = [
    "recomputed_candidate_admission_summary",
    "recomputed_envelope_summary",
    "recomputed_extraction_pressure",
    "recomputed_hard_invariants",
    "recomputed_operational_slos",
    "recomputed_planner_summary",
    "recomputed_repeatability_fingerprints",
    "recomputed_retry_summary",
    "recomputed_safe_outcome_summary",
    "recomputed_visual_input_plan_summary",
    "violating_hard_invariants_summary",
    "violating_operational_slo_summary",
]


def recomputed_candidate_admission_summary(report: dict[str, Any]) -> dict[str, Any] | None:
    documents = _document_rows(report)
    if documents is None:
        return None
    valid, document_rows = documents
    if not valid:
        return {}
    return _candidate_admission_evidence(document_rows)


def recomputed_planner_summary(report: dict[str, Any]) -> dict[str, Any] | None:
    documents = _document_rows(report)
    if documents is None:
        return None
    valid, document_rows = documents
    if not valid:
        return {}
    planner_rows = all_rows(document_rows, "planner")
    task_rows = all_rows(document_rows, "plannerTasks")
    contract_modes = Counter(
        str(get_value(row, "compatibility_mode", "compatibilityMode") or "unknown")
        for row in task_rows
    )
    return {
        "selectedTaskCount": sum_values(
            planner_rows,
            "selected_task_count",
            "selectedTaskCount",
        ),
        "skippedTaskCount": sum_values(planner_rows, "skipped_task_count", "skippedTaskCount"),
        "abstentionCount": sum_values(planner_rows, "abstention_count", "abstentionCount"),
        "missingContractCount": sum_values(
            planner_rows,
            "missing_contract_count",
            "missingContractCount",
        ),
        "missingGroundingCount": sum_values(
            planner_rows,
            "missing_grounding_count",
            "missingGroundingCount",
        ),
        "incompatibleSchemaCount": sum_values(
            planner_rows,
            "incompatible_schema_count",
            "incompatibleSchemaCount",
        ),
        "duplicateSuppressedCount": sum_values(
            planner_rows,
            "duplicate_suppressed_count",
            "duplicateSuppressedCount",
        ),
        "contractResolutionModes": dict(sorted(contract_modes.items())),
    }


def recomputed_envelope_summary(report: dict[str, Any]) -> dict[str, Any] | None:
    documents = _document_rows(report)
    if documents is None:
        return None
    valid, document_rows = documents
    if not valid:
        return {}
    envelopes = [
        envelope
        for extraction in all_rows(document_rows, "extractions")
        if (envelope := _region_envelope(extraction))
    ]
    if not envelopes:
        return None
    counts = Counter({"facts": 0, "lineItems": 0, "tableRows": 0, "observations": 0})
    concrete = 0
    total_evidence = 0
    for envelope in envelopes:
        counts["facts"] += len(list_value(get_value(envelope, "facts")))
        counts["lineItems"] += len(list_value(get_value(envelope, "line_items", "lineItems")))
        counts["tableRows"] += len(list_value(get_value(envelope, "table_rows", "tableRows")))
        counts["observations"] += len(list_value(get_value(envelope, "observations")))
        for evidence in list_value(get_value(envelope, "evidence")):
            if isinstance(evidence, dict):
                total_evidence += 1
                if bool_value(
                    get_value(evidence, "concrete", "evidence_concrete", "evidenceConcrete")
                ):
                    concrete += 1
    coverage = round(concrete / total_evidence, 4) if total_evidence else 0.0
    return {
        **dict(counts),
        "concreteEvidenceCoverage": coverage,
    }


def recomputed_visual_input_plan_summary(report: dict[str, Any]) -> dict[str, Any] | None:
    documents = _document_rows(report)
    if documents is None:
        return None
    valid, document_rows = documents
    if not valid:
        return {}
    routes: Counter[str] = Counter()
    for extraction in all_rows(document_rows, "extractions"):
        plan = dict_value(get_value(extraction, "visual_plan", "visualPlan"))
        route = get_value(plan, "route", "selectedRoute", "mode")
        if route:
            routes[str(route)] += 1
    if not routes:
        return None
    return {"routeDistribution": dict(sorted(routes.items()))}


def recomputed_retry_summary(report: dict[str, Any]) -> dict[str, Any] | None:
    documents = _document_rows(report)
    if documents is None:
        return None
    valid, document_rows = documents
    if not valid:
        return {}
    outcomes: Counter[str] = Counter()
    for extraction in all_rows(document_rows, "extractions"):
        attempts = list_value(get_value(extraction, "visual_input_attempts", "visualInputAttempts"))
        for attempt in attempts:
            if not isinstance(attempt, dict):
                continue
            outcome = get_value(attempt, "outcome", "status")
            if outcome:
                outcomes[str(outcome)] += 1
    if not outcomes:
        for job in all_rows(document_rows, "jobs"):
            status = get_value(job, "status")
            count = int_value(get_value(job, "count"), default=1)
            if status:
                outcomes[str(status)] += count
    if not outcomes:
        return None
    return {"outcomes": dict(sorted(outcomes.items()))}


def recomputed_extraction_pressure(report: dict[str, Any]) -> dict[str, Any] | None:
    documents = _document_rows(report)
    if documents is None:
        return None
    valid, document_rows = documents
    if not valid:
        return {}
    planner_rows = all_rows(document_rows, "planner")
    task_rows = all_rows(document_rows, "plannerTasks")
    if not planner_rows and not task_rows:
        return None
    selected_tasks = [
        task for task in task_rows if str(get_value(task, "status") or "").startswith("selected")
    ]
    selected_by_backend = Counter(
        str(get_value(task, "extractor_backend", "extractorBackend") or "unknown")
        for task in selected_tasks
    )
    selected_by_page = Counter(
        str(get_value(task, "page_number", "pageNumber") or "unknown") for task in selected_tasks
    )
    estimated_visual_tokens = sum(
        int_value(
            get_value(dict_value(get_value(task, "task_json", "taskJson")), "estimatedVisualTokens")
        )
        for task in task_rows
    )
    skipped_budget_count = sum(
        1 for task in task_rows if str(get_value(task, "status") or "") == "skipped_budget_exceeded"
    )
    return {
        "plannedTaskCount": sum_values(planner_rows, "selected_task_count", "selectedTaskCount")
        + sum_values(planner_rows, "skipped_task_count", "skippedTaskCount"),
        "selectedTaskCount": sum_values(planner_rows, "selected_task_count", "selectedTaskCount"),
        "selectedTaskCountByBackend": dict(sorted(selected_by_backend.items())),
        "selectedTaskCountByPage": dict(sorted(selected_by_page.items())),
        "maxTasksPerDocumentPolicy": int_value(
            first_report_value(planner_rows, "maxTasksPerDocumentPolicy")
        ),
        "maxTasksPerPagePolicy": int_value(
            first_report_value(planner_rows, "maxTasksPerPagePolicy")
        ),
        "budgetExceededCount": skipped_budget_count
        or sum_values(planner_rows, "skipped_task_count", "skippedTaskCount"),
        "estimatedVisualTokens": estimated_visual_tokens,
        "estimatedDoclingContextTokens": int_value(
            first_report_value(planner_rows, "estimatedDoclingContextTokens")
        ),
    }


def recomputed_safe_outcome_summary(report: dict[str, Any]) -> dict[str, Any] | None:
    documents = _document_rows(report)
    if documents is None:
        return None
    valid, document_rows = documents
    if not valid:
        return {}
    planner_rows = all_rows(document_rows, "planner")
    admission_events = all_rows(document_rows, "admissionEvents")
    job_rows = all_rows(document_rows, "jobs")
    if not planner_rows and not admission_events and not job_rows:
        return None
    return {
        "safeAbstentionCount": sum_values(
            planner_rows,
            "abstention_count",
            "abstentionCount",
        ),
        "safeSkipCount": sum_values(planner_rows, "skipped_task_count", "skippedTaskCount"),
        "safeRejectionCount": _candidate_admission_evidence(document_rows)["rejectedCount"],
        "unsafeFailureCount": _unsafe_failure_count(job_rows),
    }


def recomputed_hard_invariants(report: dict[str, Any]) -> dict[str, Any] | None:
    documents = _document_rows(report)
    if documents is None:
        return None
    valid, document_rows = documents
    if not valid:
        return {
            "status": "failed",
            "totalViolationCount": 1,
            "invariants": {},
        }
    return evaluate_hard_correctness_invariants(document_rows)


def recomputed_operational_slos(report: dict[str, Any]) -> dict[str, Any] | None:
    documents = _document_rows(report)
    if documents is None:
        return None
    valid, document_rows = documents
    if not valid:
        return {
            "status": "failed",
            "metrics": {"targetQueueDeadLetterCount": 1},
            "gates": {},
        }
    return evaluate_operational_slos(document_rows)


def recomputed_repeatability_fingerprints(report: dict[str, Any]) -> dict[str, str] | None:
    documents = _document_rows(report)
    if documents is None:
        return None
    valid, document_rows = documents
    if not valid:
        return {}
    run_id = str(get_value(report, "runId", "run_id") or "")
    return repeatability_fingerprints(
        document_rows,
        _candidate_rejection_summary(run_id, document_rows),
    )


def violating_hard_invariants_summary(summary: dict[str, Any]) -> dict[str, Any]:
    invariants = dict_value(get_value(summary, "invariants"))
    violating_invariants = {
        key: detail
        for key, detail in invariants.items()
        if not _is_zero_number(get_value(dict_value(detail), "violationCount", "violation_count"))
    }
    return {
        "status": get_value(summary, "status"),
        "totalViolationCount": get_value(summary, "totalViolationCount", "total_violation_count"),
        "invariants": violating_invariants,
    }


def violating_operational_slo_summary(summary: dict[str, Any]) -> dict[str, Any]:
    metrics = dict_value(get_value(summary, "metrics"))
    gates = dict_value(get_value(summary, "gates"))
    violating_gates = {
        key: detail for key, detail in sorted(gates.items()) if _slo_gate_failed(dict_value(detail))
    }
    return {
        "status": get_value(summary, "status"),
        "metrics": {
            "targetQueueDeadLetterCount": get_value(
                metrics,
                "targetQueueDeadLetterCount",
                "target_queue_dead_letter_count",
            )
        },
        "gates": violating_gates,
    }


def _document_rows(report: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]] | None:
    documents = get_value(report, "documents")
    if documents is None:
        return None
    if not isinstance(documents, list):
        return False, []
    return True, [row for row in documents if isinstance(row, dict)]


def _candidate_rejection_summary(run_id: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
    rejection_reasons: Counter[str] = Counter()
    for event in all_rows(documents, "admissionEvents"):
        decision = str(get_value(event, "decision") or "")
        if not decision.startswith("rejected"):
            continue
        reasons = list_value(get_value(event, "reasons"))
        if reasons:
            rejection_reasons.update(str(reason) for reason in reasons)
        else:
            rejection_reasons[decision] += 1
    return {
        "runId": run_id,
        "rejectionReasons": dict(sorted(rejection_reasons.items())),
    }


def _candidate_admission_evidence(documents: list[dict[str, Any]]) -> dict[str, Any]:
    admitted = 0
    rejected = 0
    rejection_reasons: Counter[str] = Counter()
    for event in all_rows(documents, "admissionEvents"):
        decision = str(get_value(event, "decision") or "")
        if decision.startswith("admitted"):
            admitted += 1
        elif decision.startswith("rejected"):
            rejected += 1
            reasons = list_value(get_value(event, "reasons"))
            if reasons:
                rejection_reasons.update(str(reason) for reason in reasons)
            else:
                rejection_reasons[decision] += 1
    return {
        "admittedCount": admitted,
        "rejectedCount": rejected,
        "rejectionReasons": dict(sorted(rejection_reasons.items())),
    }


def _unsafe_failure_count(job_rows: list[dict[str, Any]]) -> int:
    unsafe = 0
    for job in job_rows:
        status = str(get_value(job, "status") or "")
        if status in {"failed", "dead_letter", "pipeline_failed"}:
            unsafe += int_value(get_value(job, "count"), default=1)
    return unsafe


def _region_envelope(extraction: dict[str, Any]) -> dict[str, Any]:
    normalization = dict_value(get_value(extraction, "normalization_json", "normalizationJson"))
    return dict_value(get_value(normalization, "regionEnvelope", "region_envelope"))


def _slo_gate_failed(gate: dict[str, Any]) -> bool:
    return get_value(gate, "status") != "passed" or not _is_zero_number(
        get_value(gate, "violationCount", "violation_count")
    )


def _is_zero_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int | float) and value == 0
