from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_report_normalization import get_value

TARGET_FAILURE_QUEUES = frozenset(
    {"docling", "semantic-annotations", "extraction", "visual-embeddings"}
)
FAILURE_STATUSES = frozenset({"failed", "dead_letter", "pipeline_failed"})


def job_queue_name(row: dict[str, Any]) -> str:
    return str(get_value(row, "queue_name", "queueName", "queue") or "")


def job_status(row: dict[str, Any]) -> str:
    return str(get_value(row, "status") or "").lower()


def is_phase85_target_failure(row: dict[str, Any]) -> bool:
    return job_queue_name(row) in TARGET_FAILURE_QUEUES and job_status(row) in FAILURE_STATUSES
