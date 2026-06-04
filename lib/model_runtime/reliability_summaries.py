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
    sum_values,
)
from lib.model_runtime.reliability_versions import (
    CANDIDATE_GATE_VERSION,
    CONTRACT_REGISTRY_VERSION,
    PLANNER_VERSION,
    REGION_ENVELOPE_VERSION,
)


def planner_summary(run_id: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
    planner_rows = all_rows(documents, "planner")
    task_rows = all_rows(documents, "plannerTasks")
    contract_modes = Counter(
        str(get_value(row, "compatibility_mode", "compatibilityMode") or "unknown")
        for row in task_rows
    )
    return {
        "runId": run_id,
        "plannerVersion": first_value(planner_rows, "planner_version", "plannerVersion")
        or PLANNER_VERSION,
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


def candidate_admission_summary(run_id: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
    events = all_rows(documents, "admissionEvents")
    admitted = 0
    rejected = 0
    rejection_reasons: Counter[str] = Counter()
    for event in events:
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
        "runId": run_id,
        "plannerVersion": first_value(events, "planner_version", "plannerVersion")
        or PLANNER_VERSION,
        "candidateGateVersion": first_value(
            events,
            "candidate_gate_version",
            "candidateGateVersion",
        )
        or CANDIDATE_GATE_VERSION,
        "contractRegistryVersion": first_value(
            events,
            "contract_registry_version",
            "contractRegistryVersion",
        )
        or CONTRACT_REGISTRY_VERSION,
        "regionEnvelopeVersion": first_value(
            events,
            "region_envelope_version",
            "regionEnvelopeVersion",
        )
        or REGION_ENVELOPE_VERSION,
        "admittedCount": admitted,
        "rejectedCount": rejected,
        "rejectionReasons": dict(sorted(rejection_reasons.items())),
        "duplicateSuppressionCount": sum(
            1 for event in events if str(get_value(event, "decision")) == "rejected_duplicate"
        ),
    }


def contract_summary(run_id: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
    task_rows = all_rows(documents, "plannerTasks")
    schema_counts: Counter[str] = Counter()
    contract_modes: Counter[str] = Counter()
    contracted = 0
    missing = 0
    for task in task_rows:
        schema_name = get_value(task, "model_output_schema_name", "modelOutputSchemaName")
        if schema_name not in (None, ""):
            contracted += 1
            schema_counts[str(schema_name)] += 1
        else:
            missing += 1
        contract_modes[
            str(get_value(task, "compatibility_mode", "compatibilityMode") or "unknown")
        ] += 1
    return {
        "runId": run_id,
        "contractRegistryVersion": CONTRACT_REGISTRY_VERSION,
        "contractedTaskCount": contracted,
        "missingContractTaskCount": missing,
        "schemaCounts": dict(sorted(schema_counts.items())),
        "contractResolutionModes": dict(sorted(contract_modes.items())),
    }


def evidence_summary(documents: list[dict[str, Any]]) -> dict[str, Any]:
    candidate_concrete = 0
    candidate_missing = 0
    for event in all_rows(documents, "admissionEvents"):
        if bool_value(get_value(event, "evidence_concrete", "evidenceConcrete")):
            candidate_concrete += 1
        else:
            candidate_missing += 1
    envelope_evidence = _envelope_evidence_counts(documents)
    return {
        "candidateEvidenceConcreteCount": candidate_concrete,
        "candidateEvidenceMissingCount": candidate_missing,
        **envelope_evidence,
    }


def dedupe_summary(documents: list[dict[str, Any]]) -> dict[str, Any]:
    planner_duplicate_suppressed = sum_values(
        all_rows(documents, "planner"),
        "duplicate_suppressed_count",
        "duplicateSuppressedCount",
    )
    admission_duplicate_rejections = sum(
        1
        for event in all_rows(documents, "admissionEvents")
        if str(get_value(event, "decision")) == "rejected_duplicate"
    )
    return {
        "plannerDuplicateSuppressedCount": planner_duplicate_suppressed,
        "admissionDuplicateRejectionCount": admission_duplicate_rejections,
        "totalDuplicateSuppressionCount": planner_duplicate_suppressed
        + admission_duplicate_rejections,
    }


def envelope_summary(documents: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter({"facts": 0, "lineItems": 0, "tableRows": 0, "observations": 0})
    for extraction in all_rows(documents, "extractions"):
        envelope = _region_envelope(extraction)
        counts["facts"] += len(list_value(get_value(envelope, "facts")))
        counts["lineItems"] += len(list_value(get_value(envelope, "line_items", "lineItems")))
        counts["tableRows"] += len(list_value(get_value(envelope, "table_rows", "tableRows")))
        counts["observations"] += len(list_value(get_value(envelope, "observations")))
    return {
        **dict(counts),
        "concreteEvidenceCoverage": _envelope_evidence_counts(documents)[
            "concreteEvidenceCoverage"
        ],
    }


def visual_input_plan_summary(documents: list[dict[str, Any]]) -> dict[str, Any]:
    routes: Counter[str] = Counter()
    for extraction in all_rows(documents, "extractions"):
        plan = dict_value(get_value(extraction, "visual_plan", "visualPlan"))
        route = get_value(plan, "route", "selectedRoute", "mode")
        if route:
            routes[str(route)] += 1
    return {"routeDistribution": dict(sorted(routes.items()))}


def retry_summary(documents: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes: Counter[str] = Counter()
    for extraction in all_rows(documents, "extractions"):
        attempts = list_value(get_value(extraction, "visual_input_attempts", "visualInputAttempts"))
        for attempt in attempts:
            if isinstance(attempt, dict):
                outcome = get_value(attempt, "outcome", "status")
                if outcome:
                    outcomes[str(outcome)] += 1
    if not outcomes:
        for job in all_rows(documents, "jobs"):
            status = get_value(job, "status")
            count = int_value(get_value(job, "count"), default=1)
            if status:
                outcomes[str(status)] += count
    return {"outcomes": dict(sorted(outcomes.items()))}


def extraction_pressure(documents: list[dict[str, Any]]) -> dict[str, Any]:
    planner_rows = all_rows(documents, "planner")
    tasks = all_rows(documents, "plannerTasks")
    selected_tasks = [
        task for task in tasks if str(get_value(task, "status") or "").startswith("selected")
    ]
    selected_by_backend = Counter(
        str(get_value(task, "extractor_backend", "extractorBackend") or "unknown")
        for task in selected_tasks
    )
    selected_by_page = Counter(
        str(get_value(task, "page_number", "pageNumber") or "unknown") for task in selected_tasks
    )
    max_doc = first_report_value(planner_rows, "maxTasksPerDocumentPolicy")
    max_page = first_report_value(planner_rows, "maxTasksPerPagePolicy")
    estimated_visual = sum(
        int_value(
            get_value(dict_value(get_value(task, "task_json", "taskJson")), "estimatedVisualTokens")
        )
        for task in tasks
    )
    return {
        "plannedTaskCount": sum_values(planner_rows, "selected_task_count", "selectedTaskCount")
        + sum_values(planner_rows, "skipped_task_count", "skippedTaskCount"),
        "selectedTaskCount": sum_values(planner_rows, "selected_task_count", "selectedTaskCount"),
        "selectedTaskCountByBackend": dict(sorted(selected_by_backend.items())),
        "selectedTaskCountByPage": dict(sorted(selected_by_page.items())),
        "maxTasksPerDocumentPolicy": int_value(max_doc),
        "maxTasksPerPagePolicy": int_value(max_page),
        "budgetExceededCount": sum(
            1 for task in tasks if str(get_value(task, "status") or "") == "skipped_budget_exceeded"
        )
        or sum_values(planner_rows, "skipped_task_count", "skippedTaskCount"),
        "estimatedVisualTokens": estimated_visual,
        "estimatedDoclingContextTokens": int_value(
            first_report_value(planner_rows, "estimatedDoclingContextTokens")
        ),
    }


def safe_outcome_summary(
    planner: dict[str, Any],
    admission: dict[str, Any],
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    unsafe_failures = 0
    for job in all_rows(documents, "jobs"):
        if is_phase85_target_failure(job):
            unsafe_failures += int_value(get_value(job, "count"), default=1)
    return {
        "safeAbstentionCount": int_value(planner.get("abstentionCount")),
        "safeSkipCount": int_value(planner.get("skippedTaskCount")),
        "safeRejectionCount": int_value(admission.get("rejectedCount")),
        "unsafeFailureCount": unsafe_failures,
    }


def quality_summary(documents: list[dict[str, Any]]) -> dict[str, Any]:
    statuses: Counter[str] = Counter()
    review_required = 0
    for doc in documents:
        document = dict_value(get_value(doc, "document"))
        status = str(get_value(document, "review_status", "reviewStatus") or "unknown")
        statuses[status] += 1
        semantic_review = any(
            bool_value(get_value(row, "review_required", "reviewRequired"))
            for row in list_value(get_value(doc, "semantic"))
            if isinstance(row, dict)
        )
        extraction_review = any(
            str(get_value(row, "review_status", "reviewStatus") or "") == "needs_review"
            for row in list_value(get_value(doc, "extractions"))
            if isinstance(row, dict)
        )
        if status == "needs_review" or semantic_review or extraction_review:
            review_required += 1
    return {
        "documents": len(documents),
        "reviewRequiredDocuments": review_required,
        "reviewStatusCounts": dict(sorted(statuses.items())),
    }


def _region_envelope(extraction: dict[str, Any]) -> dict[str, Any]:
    normalization = dict_value(get_value(extraction, "normalization_json", "normalizationJson"))
    return dict_value(get_value(normalization, "regionEnvelope", "region_envelope"))


def _envelope_evidence_counts(documents: list[dict[str, Any]]) -> dict[str, Any]:
    concrete = 0
    total_evidence = 0
    for extraction in all_rows(documents, "extractions"):
        envelope = _region_envelope(extraction)
        for evidence in list_value(get_value(envelope, "evidence")):
            if isinstance(evidence, dict):
                total_evidence += 1
                if bool_value(
                    get_value(evidence, "concrete", "evidence_concrete", "evidenceConcrete")
                ):
                    concrete += 1
    coverage = round(concrete / total_evidence, 4) if total_evidence else 0.0
    return {
        "regionEnvelopeEvidenceCount": total_evidence,
        "regionEnvelopeConcreteEvidenceCount": concrete,
        "concreteEvidenceCoverage": coverage,
    }
