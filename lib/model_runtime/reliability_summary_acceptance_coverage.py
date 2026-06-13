from __future__ import annotations

from typing import Any

REQUIRED_REPORT_SUMMARIES = (
    "runManifest",
    "plannerSummary",
    "candidateAdmissionSummary",
    "contractSummary",
    "evidenceSummary",
    "dedupeSummary",
    "envelopeSummary",
    "visualInputPlanSummary",
    "retrySummary",
    "extractionPressure",
    "safeOutcomeSummary",
    "qualitySummary",
    "documentOutcomeSummary",
    "repeatabilityFingerprints",
    "acceptanceGates",
)
REPORT_SUMMARY_ACCEPTANCE_COVERAGE = {
    "runManifest": ("reportLineage",),
    "plannerSummary": ("plannerSummary",),
    "candidateAdmissionSummary": ("candidateAdmissionSummary",),
    "contractSummary": ("contractSummary",),
    "evidenceSummary": ("evidenceSummary",),
    "dedupeSummary": ("dedupeSummary",),
    "envelopeSummary": ("envelopeSummary",),
    "visualInputPlanSummary": ("visualInputPlanSummary",),
    "retrySummary": ("retrySummary",),
    "extractionPressure": ("extractionPressure",),
    "safeOutcomeSummary": ("safeOutcomeSummary",),
    "qualitySummary": ("qualitySummary",),
    "documentOutcomeSummary": ("documentOutcomes",),
    "repeatabilityFingerprints": ("repeatabilityFingerprints",),
    "acceptanceGates": (
        "hardCorrectnessInvariants",
        "operationalSLOs",
        "goldCorpusQuality",
    ),
}

__all__ = [
    "REPORT_SUMMARY_ACCEPTANCE_COVERAGE",
    "REQUIRED_REPORT_SUMMARIES",
    "summary_acceptance_coverage_check",
]


def summary_acceptance_coverage_check(
    checks: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    required = set(REQUIRED_REPORT_SUMMARIES)
    coverage = REPORT_SUMMARY_ACCEPTANCE_COVERAGE
    missing_summaries = sorted(required.difference(coverage))
    extra_summaries = sorted(set(coverage).difference(required))
    missing_checks = {
        summary_key: [check for check in check_names if check not in checks]
        for summary_key, check_names in coverage.items()
        if any(check not in checks for check in check_names)
    }
    empty_coverage = sorted(
        summary_key for summary_key, check_names in coverage.items() if not check_names
    )
    failures = {
        "missingSummaries": missing_summaries,
        "extraSummaries": extra_summaries,
        "missingChecks": missing_checks,
        "emptyCoverage": empty_coverage,
    }
    return {
        "status": "passed" if not any(failures.values()) else "failed",
        **failures,
    }
