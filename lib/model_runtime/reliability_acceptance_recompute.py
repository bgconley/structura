from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_invariants import evaluate_hard_correctness_invariants
from lib.model_runtime.reliability_operational_slos import evaluate_operational_slos
from lib.model_runtime.reliability_report_normalization import dict_value, get_value

__all__ = [
    "recomputed_hard_invariants",
    "recomputed_operational_slos",
    "violating_hard_invariants_summary",
    "violating_operational_slo_summary",
]


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


def _slo_gate_failed(gate: dict[str, Any]) -> bool:
    return get_value(gate, "status") != "passed" or not _is_zero_number(
        get_value(gate, "violationCount", "violation_count")
    )


def _is_zero_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int | float) and value == 0
