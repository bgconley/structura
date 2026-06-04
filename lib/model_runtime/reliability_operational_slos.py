from __future__ import annotations

from collections import Counter
from typing import Any

from lib.model_runtime.reliability_job_scope import (
    FAILURE_STATUSES,
    TARGET_FAILURE_QUEUES,
    job_queue_name,
    job_status,
)
from lib.model_runtime.reliability_report_normalization import (
    all_rows,
    bool_value,
    dict_value,
    first_report_value,
    get_value,
    int_value,
    list_value,
    normalized_text,
)

SELECTED_TASK_STATUSES = frozenset({"selected", "enqueued", "queued", "running", "completed"})
DEFAULT_THRESHOLDS = {
    "targetQueueDeadLetters": 0,
    "runtimeFailureRateMax": 0.0,
    "retrySuccessRateMin": 1.0,
    "maxTasksPerDocument": 6,
    "maxTasksPerPage": 3,
}

__all__ = ["TARGET_FAILURE_QUEUES", "evaluate_operational_slos"]


def evaluate_operational_slos(
    documents: list[dict[str, Any]],
    *,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    jobs = all_rows(documents, "jobs")
    violations = _empty_violations()

    runtime_rates = _runtime_failure_rates(jobs)
    retry_metrics = _retry_metrics(jobs)
    target_dead_letters = _target_dead_letters(jobs)

    _evaluate_target_dead_letters(target_dead_letters, resolved_thresholds, violations)
    _evaluate_classified_failures(jobs, violations)
    _evaluate_retry_success(retry_metrics, resolved_thresholds, violations)
    _evaluate_runtime_failure_rates(runtime_rates, resolved_thresholds, violations)
    _evaluate_fanout(documents, resolved_thresholds, violations)
    _evaluate_retry_safety(jobs, violations)

    gates = _gate_results(violations)
    return {
        "status": "passed"
        if all(gate["status"] == "passed" for gate in gates.values())
        else "failed",
        "thresholds": resolved_thresholds,
        "metrics": {
            "targetQueueDeadLetterCount": sum(_job_count(row) for row in target_dead_letters),
            "runtimeFailureRates": runtime_rates,
            **retry_metrics,
        },
        "gates": gates,
    }


def _empty_violations() -> dict[str, list[dict[str, Any]]]:
    return {
        "targetQueueDeadLetters": [],
        "classifiedOperationalFailures": [],
        "retrySuccessRate": [],
        "runtimeFailureRates": [],
        "runawayFanout": [],
        "retrySafeJobs": [],
    }


def _target_dead_letters(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in jobs
        if _queue(row) in TARGET_FAILURE_QUEUES and _status(row) == "dead_letter"
    ]


def _evaluate_target_dead_letters(
    target_dead_letters: list[dict[str, Any]],
    thresholds: dict[str, Any],
    violations: dict[str, list[dict[str, Any]]],
) -> None:
    allowed = int_value(thresholds.get("targetQueueDeadLetters"))
    count = sum(_job_count(row) for row in target_dead_letters)
    if count <= allowed:
        return
    for row in target_dead_letters:
        _add_violation(
            violations,
            "targetQueueDeadLetters",
            row,
            "target_queue_dead_letter",
        )


def _evaluate_classified_failures(
    jobs: list[dict[str, Any]],
    violations: dict[str, list[dict[str, Any]]],
) -> None:
    for row in jobs:
        if _status(row) not in FAILURE_STATUSES:
            continue
        unclassified = _job_count(row) - _classified_failure_count(row)
        if unclassified > 0:
            _add_violation(
                violations,
                "classifiedOperationalFailures",
                row,
                "operational_failure_missing_taxonomy_code",
                count=unclassified,
            )


def _evaluate_retry_success(
    retry_metrics: dict[str, Any],
    thresholds: dict[str, Any],
    violations: dict[str, list[dict[str, Any]]],
) -> None:
    retry_count = int_value(retry_metrics.get("retryAttemptCount"))
    if retry_count == 0:
        return
    required = float(thresholds["retrySuccessRateMin"])
    observed = float(retry_metrics["retrySuccessRate"])
    if observed < required:
        violations["retrySuccessRate"].append(
            {
                "reason": "retry_success_rate_below_threshold",
                "observed": observed,
                "required": required,
            }
        )


def _evaluate_runtime_failure_rates(
    runtime_rates: dict[str, float],
    thresholds: dict[str, Any],
    violations: dict[str, list[dict[str, Any]]],
) -> None:
    allowed = float(thresholds["runtimeFailureRateMax"])
    for queue, rate in runtime_rates.items():
        if rate > allowed:
            violations["runtimeFailureRates"].append(
                {
                    "reason": "runtime_failure_rate_above_threshold",
                    "queueName": queue,
                    "observed": rate,
                    "allowed": allowed,
                }
            )


def _evaluate_fanout(
    documents: list[dict[str, Any]],
    thresholds: dict[str, Any],
    violations: dict[str, list[dict[str, Any]]],
) -> None:
    for doc in documents:
        document = dict_value(get_value(doc, "document"))
        planner_rows = list_value(get_value(doc, "planner"))
        task_rows = [
            row
            for row in list_value(get_value(doc, "plannerTasks"))
            if isinstance(row, dict) and _task_is_selected(row)
        ]
        max_doc = int_value(
            first_report_value(planner_rows, "maxTasksPerDocumentPolicy"),
            default=int_value(thresholds.get("maxTasksPerDocument")),
        )
        max_page = int_value(
            first_report_value(planner_rows, "maxTasksPerPagePolicy"),
            default=int_value(thresholds.get("maxTasksPerPage")),
        )
        selected_count = sum(
            int_value(get_value(row, "selected_task_count", "selectedTaskCount"))
            for row in planner_rows
            if isinstance(row, dict)
        ) or len(task_rows)
        if max_doc and selected_count > max_doc:
            violations["runawayFanout"].append(
                {
                    "reason": "selected_tasks_exceed_document_policy",
                    "documentId": get_value(document, "id", "documentId"),
                    "selectedTaskCount": selected_count,
                    "maxTasksPerDocumentPolicy": max_doc,
                }
            )
        page_counts = Counter(
            normalized_text(get_value(row, "page_number", "pageNumber")) or "unknown"
            for row in task_rows
        )
        for page, count in sorted(page_counts.items()):
            if max_page and count > max_page:
                violations["runawayFanout"].append(
                    {
                        "reason": "selected_tasks_exceed_page_policy",
                        "documentId": get_value(document, "id", "documentId"),
                        "pageNumber": page,
                        "selectedTaskCount": count,
                        "maxTasksPerPagePolicy": max_page,
                    }
                )


def _evaluate_retry_safety(
    jobs: list[dict[str, Any]],
    violations: dict[str, list[dict[str, Any]]],
) -> None:
    for row in jobs:
        if _status(row) not in FAILURE_STATUSES:
            continue
        attempt_count = _attempt_count(row)
        max_attempts = int_value(get_value(row, "max_attempts", "maxAttempts"))
        if max_attempts and attempt_count > max_attempts:
            _add_violation(
                violations,
                "retrySafeJobs",
                row,
                "attempt_count_exceeds_max_attempts",
            )
            continue
        if _retryable_flag(row) is None:
            _add_violation(
                violations,
                "retrySafeJobs",
                row,
                "operational_failure_missing_retryable_flag",
            )


def _runtime_failure_rates(jobs: list[dict[str, Any]]) -> dict[str, float]:
    totals: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    for row in jobs:
        queue = _queue(row)
        if queue not in TARGET_FAILURE_QUEUES:
            continue
        count = _job_count(row)
        totals[queue] += count
        if _status(row) in FAILURE_STATUSES:
            failures[queue] += count
    return {
        queue: round(failures[queue] / total, 4) if total else 0.0
        for queue, total in sorted(totals.items())
    }


def _retry_metrics(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    retry_count = 0
    retry_success = 0
    for row in jobs:
        if _attempt_count(row) <= _job_count(row):
            continue
        count = _job_count(row)
        retry_count += count
        if _status(row) == "succeeded":
            retry_success += count
    rate = round(retry_success / retry_count, 4) if retry_count else 1.0
    return {
        "retryAttemptCount": retry_count,
        "retrySucceededCount": retry_success,
        "retrySuccessRate": rate,
    }


def _gate_results(violations: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    return {
        key: {
            "status": "passed" if not rows else "failed",
            "violationCount": len(rows),
            "examples": rows[:10],
        }
        for key, rows in violations.items()
    }


def _task_is_selected(row: dict[str, Any]) -> bool:
    return normalized_text(get_value(row, "status")) in SELECTED_TASK_STATUSES


def _queue(row: dict[str, Any]) -> str:
    return job_queue_name(row)


def _status(row: dict[str, Any]) -> str:
    return job_status(row)


def _job_count(row: dict[str, Any]) -> int:
    return int_value(get_value(row, "count"), default=1)


def _attempt_count(row: dict[str, Any]) -> int:
    return int_value(get_value(row, "attempt_count", "attemptCount"), default=_job_count(row))


def _classified_failure_count(row: dict[str, Any]) -> int:
    errors = _error_jsons(row)
    if errors:
        return sum(1 for error in errors if _has_taxonomy_code(error))
    return _job_count(row) if _has_taxonomy_code(row) else 0


def _error_jsons(row: dict[str, Any]) -> list[dict[str, Any]]:
    errors = list_value(get_value(row, "error_jsons", "errorJsons"))
    if errors:
        return [error for error in errors if isinstance(error, dict)]
    error = dict_value(get_value(row, "error_json", "errorJson"))
    return [error] if error else []


def _has_taxonomy_code(mapping: dict[str, Any]) -> bool:
    details = dict_value(get_value(mapping, "details"))
    return any(
        get_value(
            source,
            "taxonomy_code",
            "taxonomyCode",
            "failure_taxonomy",
            "failureTaxonomy",
            "failure_code",
            "failureCode",
        )
        for source in (mapping, details)
    )


def _retryable_flag(row: dict[str, Any]) -> bool | None:
    for source in [row, *_error_jsons(row)]:
        value = get_value(source, "retryable")
        if value is not None:
            return bool_value(value)
    return None


def _add_violation(
    violations: dict[str, list[dict[str, Any]]],
    key: str,
    row: dict[str, Any],
    reason: str,
    *,
    count: int | None = None,
) -> None:
    violations[key].append(
        {
            "reason": reason,
            "queueName": _queue(row),
            "jobType": normalized_text(get_value(row, "job_type", "jobType")) or "unknown",
            "status": _status(row),
            "count": count if count is not None else _job_count(row),
        }
    )
