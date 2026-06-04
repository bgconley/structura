from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_acceptance_recompute import recomputed_envelope_summary
from lib.model_runtime.reliability_report_normalization import dict_value, get_value, snake

_ENVELOPE_SUMMARY_KEYS = (
    "facts",
    "lineItems",
    "tableRows",
    "observations",
    "concreteEvidenceCoverage",
)


def envelope_summary_acceptance_check(reports: list[dict[str, Any]]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    for index, report in enumerate(reports):
        summary = dict_value(get_value(report, "envelopeSummary"))
        recomputed = recomputed_envelope_summary(report)
        if recomputed is None:
            continue
        invalid = [
            key
            for key in _ENVELOPE_SUMMARY_KEYS
            if get_value(summary, key, snake(key)) != get_value(recomputed, key, snake(key))
        ]
        if invalid:
            failures.append(
                {
                    "reportIndex": index,
                    "runId": get_value(report, "runId", "run_id"),
                    "invalid": invalid,
                    "details": summary,
                    "recomputed": recomputed,
                }
            )
    return {
        "status": "passed" if reports and not failures else "failed",
        "failures": failures,
    }
