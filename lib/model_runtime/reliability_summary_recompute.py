from __future__ import annotations

from collections import Counter
from typing import Any

from lib.model_runtime.reliability_job_scope import is_phase85_target_failure
from lib.model_runtime.reliability_report_normalization import (
    all_rows,
    bool_value,
    dict_value,
    first_report_value,
    first_value,
    get_value,
    int_value,
    list_value,
    normalized_decision,
    normalized_text,
    sum_values,
)
from lib.model_runtime.reliability_summaries import (
    contract_summary,
    dedupe_summary,
    evidence_summary,
)

__all__ = [
    "candidate_rejection_summary",
    "recomputed_candidate_admission_summary",
    "recomputed_contract_summary",
    "recomputed_dedupe_summary",
    "recomputed_envelope_summary",
    "recomputed_evidence_summary",
    "recomputed_extraction_pressure",
    "recomputed_planner_summary",
    "recomputed_quality_summary",
    "recomputed_retry_summary",
    "recomputed_safe_outcome_summary",
    "recomputed_visual_input_plan_summary",
    "report_document_rows",
]


def recomputed_candidate_admission_summary(report: dict[str, Any]) -> dict[str, Any] | None:
    documents = report_document_rows(report)
    if documents is None:
        return None
    valid, document_rows = documents
    if not valid:
        return {}
    return {
        **_candidate_admission_lineage(report, document_rows),
        **_candidate_admission_evidence(document_rows),
    }


def recomputed_contract_summary(report: dict[str, Any]) -> dict[str, Any] | None:
    documents = report_document_rows(report)
    if documents is None:
        return None
    valid, document_rows = documents
    if not valid:
        return {}
    return contract_summary(str(_report_run_id(report) or ""), document_rows)


def recomputed_evidence_summary(report: dict[str, Any]) -> dict[str, Any] | None:
    documents = report_document_rows(report)
    if documents is None:
        return None
    valid, document_rows = documents
    if not valid:
        return {}
    return evidence_summary(document_rows)


def recomputed_dedupe_summary(report: dict[str, Any]) -> dict[str, Any] | None:
    documents = report_document_rows(report)
    if documents is None:
        return None
    valid, document_rows = documents
    if not valid:
        return {}
    return dedupe_summary(document_rows)


def recomputed_planner_summary(report: dict[str, Any]) -> dict[str, Any] | None:
    documents = report_document_rows(report)
    if documents is None:
        return None
    valid, document_rows = documents
    if not valid:
        return {}
    planner_rows = all_rows(document_rows, "planner")
    task_rows = all_rows(document_rows, "plannerTasks")
    contract_modes = Counter(
        normalized_text(get_value(row, "compatibility_mode", "compatibilityMode")) or "unknown"
        for row in task_rows
    )
    return {
        "runId": _report_run_id(report),
        "plannerVersion": first_value(planner_rows, "planner_version", "plannerVersion")
        or _run_manifest_value(report, "planner_version", "plannerVersion"),
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
    documents = report_document_rows(report)
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
    documents = report_document_rows(report)
    if documents is None:
        return None
    valid, document_rows = documents
    if not valid:
        return {}
    routes: Counter[str] = Counter()
    for extraction in all_rows(document_rows, "extractions"):
        plan = dict_value(get_value(extraction, "visual_plan", "visualPlan"))
        route = normalized_text(get_value(plan, "route", "selectedRoute", "mode"))
        if route:
            routes[route] += 1
    if not routes:
        return None
    return {"routeDistribution": dict(sorted(routes.items()))}


def recomputed_retry_summary(report: dict[str, Any]) -> dict[str, Any] | None:
    documents = report_document_rows(report)
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
            outcome = normalized_text(get_value(attempt, "outcome", "status"))
            if outcome:
                outcomes[outcome] += 1
    if not outcomes:
        for job in all_rows(document_rows, "jobs"):
            status = normalized_text(get_value(job, "status"))
            count = int_value(get_value(job, "count"), default=1)
            if status:
                outcomes[status] += count
    if not outcomes:
        return None
    return {"outcomes": dict(sorted(outcomes.items()))}


def recomputed_extraction_pressure(report: dict[str, Any]) -> dict[str, Any] | None:
    documents = report_document_rows(report)
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
        task
        for task in task_rows
        if normalized_text(get_value(task, "status")).startswith("selected")
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
        1
        for task in task_rows
        if normalized_text(get_value(task, "status")) == "skipped_budget_exceeded"
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
    documents = report_document_rows(report)
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


def recomputed_quality_summary(report: dict[str, Any]) -> dict[str, Any] | None:
    documents = report_document_rows(report)
    if documents is None:
        return None
    valid, document_rows = documents
    if not valid:
        return {}
    statuses: Counter[str] = Counter()
    review_required = 0
    for row in document_rows:
        document = dict_value(get_value(row, "document"))
        status = normalized_text(get_value(document, "review_status", "reviewStatus")) or "unknown"
        statuses[status] += 1
        semantic_review = any(
            bool_value(get_value(semantic, "review_required", "reviewRequired"))
            for semantic in list_value(get_value(row, "semantic"))
            if isinstance(semantic, dict)
        )
        extraction_review = any(
            normalized_text(get_value(extraction, "review_status", "reviewStatus"))
            == "needs_review"
            for extraction in list_value(get_value(row, "extractions"))
            if isinstance(extraction, dict)
        )
        if status == "needs_review" or semantic_review or extraction_review:
            review_required += 1
    return {
        "documents": len(document_rows),
        "reviewRequiredDocuments": review_required,
        "reviewStatusCounts": dict(sorted(statuses.items())),
    }


def report_document_rows(report: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]] | None:
    documents = get_value(report, "documents")
    if documents is None:
        return None
    if not isinstance(documents, list):
        return False, []
    return True, [row for row in documents if isinstance(row, dict)]


def candidate_rejection_summary(run_id: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
    rejection_reasons: Counter[str] = Counter()
    for event in all_rows(documents, "admissionEvents"):
        decision = normalized_decision(get_value(event, "decision"))
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
        decision = normalized_decision(get_value(event, "decision"))
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
        "duplicateSuppressionCount": sum(
            1
            for event in all_rows(documents, "admissionEvents")
            if normalized_decision(get_value(event, "decision")) == "rejected_duplicate"
        ),
    }


def _candidate_admission_lineage(
    report: dict[str, Any],
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    events = all_rows(documents, "admissionEvents")
    return {
        "runId": _report_run_id(report),
        "plannerVersion": first_value(events, "planner_version", "plannerVersion")
        or _run_manifest_value(report, "planner_version", "plannerVersion"),
        "candidateGateVersion": first_value(
            events,
            "candidate_gate_version",
            "candidateGateVersion",
        )
        or _run_manifest_value(report, "candidate_gate_version", "candidateGateVersion"),
        "contractRegistryVersion": first_value(
            events,
            "contract_registry_version",
            "contractRegistryVersion",
        )
        or _run_manifest_value(report, "contract_registry_version", "contractRegistryVersion"),
        "regionEnvelopeVersion": first_value(
            events,
            "region_envelope_version",
            "regionEnvelopeVersion",
        )
        or _run_manifest_value(report, "region_envelope_version", "regionEnvelopeVersion"),
    }


def _unsafe_failure_count(job_rows: list[dict[str, Any]]) -> int:
    unsafe = 0
    for job in job_rows:
        if is_phase85_target_failure(job):
            unsafe += int_value(get_value(job, "count"), default=1)
    return unsafe


def _region_envelope(extraction: dict[str, Any]) -> dict[str, Any]:
    normalization = dict_value(get_value(extraction, "normalization_json", "normalizationJson"))
    return dict_value(get_value(normalization, "regionEnvelope", "region_envelope"))


def _report_run_id(report: dict[str, Any]) -> Any:
    return get_value(report, "runId", "run_id")


def _run_manifest_value(report: dict[str, Any], snake_key: str, camel_key: str) -> Any:
    manifest = dict_value(get_value(report, "runManifest", "run_manifest"))
    return get_value(manifest, snake_key, camel_key)
