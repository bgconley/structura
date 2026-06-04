from __future__ import annotations

from pathlib import Path
from typing import Any

ALLOWED_EVIDENCE_REPORT_STATUSES = frozenset({"passed", "not_required", "not_evaluated"})
EVIDENCE_REPORT_STATUS_CONTAINERS = ("checks", "acceptanceGates")

__all__ = ["assert_model_corpus_report_statuses_pass"]


def assert_model_corpus_report_statuses_pass(
    section: str,
    artifact: dict[str, Any],
    path: Path,
) -> None:
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
