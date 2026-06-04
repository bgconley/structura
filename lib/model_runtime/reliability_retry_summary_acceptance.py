from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_acceptance_recompute import (
    recomputed_retry_summary,
)
from lib.model_runtime.reliability_report_normalization import dict_value, get_value


def retry_summary_acceptance_check(reports: list[dict[str, Any]]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for index, report in enumerate(reports):
        summary = dict_value(get_value(report, "retrySummary"))
        recomputed = recomputed_retry_summary(report)
        if recomputed is None:
            continue
        if get_value(summary, "outcomes") != get_value(recomputed, "outcomes"):
            failures.append(
                {
                    "reportIndex": index,
                    "runId": get_value(report, "runId", "run_id"),
                    "invalid": ["outcomes"],
                    "details": summary,
                    "recomputed": recomputed,
                }
            )
    return {
        "status": "passed" if reports and not failures else "failed",
        "failures": failures,
    }
