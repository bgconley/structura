from __future__ import annotations

import math
from pathlib import Path
from typing import Any

ALLOWED_EVIDENCE_REPORT_STATUSES = frozenset({"passed", "not_required"})
EVIDENCE_REPORT_STATUS_CONTAINERS = ("checks", "acceptanceGates")
REPORT_PROBLEM_LIST_KEYS = frozenset(
    {
        "failedMetrics",
        "failures",
        "invalid",
        "missing",
        "missingByReport",
        "missingMetrics",
        "drift",
    }
)
REPORT_PROBLEM_COUNT_KEYS = frozenset(
    {
        "failedCount",
        "failureCount",
        "invalidCount",
        "missingCount",
        "targetQueueDeadLetterCount",
        "totalViolationCount",
        "violationCount",
    }
)

__all__ = ["assert_model_corpus_report_statuses_pass"]


def assert_model_corpus_report_statuses_pass(
    section: str,
    artifact: dict[str, Any],
    path: Path,
) -> None:
    failure_lists = [
        failure_path for failure_path, failures in _iter_report_failure_lists(artifact) if failures
    ]
    if failure_lists:
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath has report failures "
            f"{failure_lists[0]}: {path}"
        )
    invalid_counts = _iter_invalid_report_problem_counts(artifact)
    if invalid_counts:
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath has invalid report problem "
            f"counter {invalid_counts[0]}: {path}"
        )
    problem_counts = [
        count_path for count_path, count in _iter_report_problem_counts(artifact) if count > 0
    ]
    if problem_counts:
        raise SystemExit(
            f"Model corpus evidence {section} evidencePath has positive report problem "
            f"counter {problem_counts[0]}: {path}"
        )
    invalid = [
        (status_path, status)
        for status_path, status in _iter_report_statuses(artifact)
        if status not in ALLOWED_EVIDENCE_REPORT_STATUSES
    ]
    if not invalid:
        return
    status_path, status = invalid[0]
    raise SystemExit(
        f"Model corpus evidence {section} evidencePath has non-passing report status "
        f"{status_path}={status!r}: {path}"
    )


def _iter_report_statuses(artifact: dict[str, Any]) -> list[tuple[str, str]]:
    statuses: list[tuple[str, str]] = []
    if isinstance(artifact.get("status"), str):
        statuses.append(("status", str(artifact["status"]).strip()))
    for container_key in EVIDENCE_REPORT_STATUS_CONTAINERS:
        container = artifact.get(container_key)
        if isinstance(container, dict):
            statuses.extend(_iter_nested_statuses(container, prefix=container_key))
    return statuses


def _iter_report_failure_lists(artifact: dict[str, Any]) -> list[tuple[str, list[Any]]]:
    failures: list[tuple[str, list[Any]]] = []
    for key in REPORT_PROBLEM_LIST_KEYS:
        if isinstance(artifact.get(key), list):
            failures.append((key, list(artifact[key])))
    for container_key in EVIDENCE_REPORT_STATUS_CONTAINERS:
        container = artifact.get(container_key)
        if isinstance(container, dict):
            failures.extend(_iter_nested_failure_lists(container, prefix=container_key))
    return failures


def _iter_nested_failure_lists(value: Any, *, prefix: str) -> list[tuple[str, list[Any]]]:
    failures: list[tuple[str, list[Any]]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}"
            if key in REPORT_PROBLEM_LIST_KEYS and isinstance(item, list):
                failures.append((path, list(item)))
            elif isinstance(item, dict | list):
                failures.extend(_iter_nested_failure_lists(item, prefix=path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, dict | list):
                failures.extend(_iter_nested_failure_lists(item, prefix=f"{prefix}[{index}]"))
    return failures


def _iter_report_problem_counts(artifact: dict[str, Any]) -> list[tuple[str, float]]:
    counts: list[tuple[str, float]] = []
    for key in REPORT_PROBLEM_COUNT_KEYS & artifact.keys():
        count = _numeric_count(artifact[key])
        if count is not None:
            counts.append((key, count))
    for container_key in EVIDENCE_REPORT_STATUS_CONTAINERS:
        container = artifact.get(container_key)
        if isinstance(container, dict):
            counts.extend(_iter_nested_problem_counts(container, prefix=container_key))
    return counts


def _iter_invalid_report_problem_counts(artifact: dict[str, Any]) -> list[str]:
    invalid: list[str] = []
    for key in REPORT_PROBLEM_COUNT_KEYS & artifact.keys():
        if _numeric_count(artifact[key]) is None:
            invalid.append(key)
    for container_key in EVIDENCE_REPORT_STATUS_CONTAINERS:
        container = artifact.get(container_key)
        if isinstance(container, dict):
            invalid.extend(_iter_nested_invalid_problem_counts(container, prefix=container_key))
    return invalid


def _iter_nested_problem_counts(value: Any, *, prefix: str) -> list[tuple[str, float]]:
    counts: list[tuple[str, float]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}"
            count = _numeric_count(item)
            if key in REPORT_PROBLEM_COUNT_KEYS and count is not None:
                counts.append((path, count))
            elif isinstance(item, dict | list):
                counts.extend(_iter_nested_problem_counts(item, prefix=path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, dict | list):
                counts.extend(_iter_nested_problem_counts(item, prefix=f"{prefix}[{index}]"))
    return counts


def _iter_nested_invalid_problem_counts(value: Any, *, prefix: str) -> list[str]:
    invalid: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}"
            if key in REPORT_PROBLEM_COUNT_KEYS:
                if _numeric_count(item) is None:
                    invalid.append(path)
            elif isinstance(item, dict | list):
                invalid.extend(_iter_nested_invalid_problem_counts(item, prefix=path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, dict | list):
                invalid.extend(
                    _iter_nested_invalid_problem_counts(item, prefix=f"{prefix}[{index}]")
                )
    return invalid


def _numeric_count(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
        if math.isfinite(number) and number >= 0:
            return number
    return None


def _iter_nested_statuses(value: Any, *, prefix: str) -> list[tuple[str, str]]:
    statuses: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}"
            if key == "status" and isinstance(item, str):
                statuses.append((path, item.strip()))
            elif isinstance(item, dict | list):
                statuses.extend(_iter_nested_statuses(item, prefix=path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, dict | list):
                statuses.extend(_iter_nested_statuses(item, prefix=f"{prefix}[{index}]"))
    return statuses
