from __future__ import annotations

from lib.model_runtime.reliability_acceptance import (
    REPORT_SUMMARY_ACCEPTANCE_COVERAGE,
    REQUIRED_REPORT_SUMMARIES,
    evaluate_phase85_report_acceptance,
)


def test_required_report_summaries_have_substantive_acceptance_coverage() -> None:
    summary = evaluate_phase85_report_acceptance([])
    checks = set(summary["checks"])

    assert set(REPORT_SUMMARY_ACCEPTANCE_COVERAGE) == set(REQUIRED_REPORT_SUMMARIES)
    for summary_key, check_names in REPORT_SUMMARY_ACCEPTANCE_COVERAGE.items():
        assert check_names, summary_key
        assert set(check_names) <= checks, summary_key
    assert summary["checks"]["summaryAcceptanceCoverage"]["status"] == "passed"
