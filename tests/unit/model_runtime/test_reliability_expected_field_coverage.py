from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_report import build_phase85_reliability_report
from lib.model_runtime.reliability_summaries import expected_field_coverage_summary


def _document_with_extractions(extractions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "document": {"id": "doc-1", "review_status": "needs_review"},
        "jobs": [],
        "semantic": [],
        "semanticRegions": [],
        "planner": [],
        "plannerTasks": [],
        "admissionEvents": [],
        "extractions": extractions,
        "fields": [],
        "lineItems": [],
        "observations": [],
        "embeddings": [],
        "reviewTasks": [],
    }


def _region_extraction(
    coverage: dict[str, Any] | None,
    *,
    is_current: bool = True,
    extraction_scope: str = "semantic_region",
) -> dict[str, Any]:
    normalization: dict[str, Any] = {}
    if coverage is not None:
        normalization["expected_field_coverage"] = coverage
    return {
        "schema_name": "receipt",
        "extraction_scope": extraction_scope,
        "is_current": is_current,
        "normalization_json": normalization,
    }


def test_expected_field_coverage_summary_aggregates_current_region_rows() -> None:
    documents = [
        _document_with_extractions(
            [
                _region_extraction(
                    {
                        "expected": ["total_amount", "payment_method"],
                        "produced": ["receipt.transaction.total"],
                        "missing": ["payment_method"],
                        "coverage_ratio": 0.5,
                    }
                ),
                _region_extraction(
                    {
                        "expected": ["vin", "mileage"],
                        "produced": [],
                        "missing": ["vin", "mileage"],
                        "coverage_ratio": 0.0,
                    }
                ),
                _region_extraction(
                    {
                        "expected": ["invoice_number"],
                        "produced": ["invoice.invoice_number"],
                        "missing": [],
                        "coverage_ratio": 1.0,
                    }
                ),
                # Superseded and non-region rows must not count.
                _region_extraction(
                    {
                        "expected": ["ignored"],
                        "produced": [],
                        "missing": ["ignored"],
                        "coverage_ratio": 0.0,
                    },
                    is_current=False,
                ),
                _region_extraction(
                    {
                        "expected": ["ignored"],
                        "produced": [],
                        "missing": ["ignored"],
                        "coverage_ratio": 0.0,
                    },
                    extraction_scope="aggregate",
                ),
                # Current region row without expected fields recorded.
                _region_extraction(None),
            ]
        )
    ]

    summary = expected_field_coverage_summary(documents)

    assert summary["currentRegionExtractionCount"] == 4
    assert summary["regionsWithExpectedFields"] == 3
    assert summary["fullyCoveredRegionCount"] == 1
    assert summary["partiallyCoveredRegionCount"] == 1
    assert summary["uncoveredRegionCount"] == 1
    assert summary["expectedFieldCount"] == 5
    assert summary["producedExpectedFieldCount"] == 2
    assert summary["missingExpectedFieldCount"] == 3
    assert summary["meanCoverageRatio"] == 0.5
    assert summary["missingFieldCounts"] == {"mileage": 1, "payment_method": 1, "vin": 1}


def test_expected_field_coverage_summary_handles_empty_documents() -> None:
    summary = expected_field_coverage_summary([])

    assert summary["currentRegionExtractionCount"] == 0
    assert summary["regionsWithExpectedFields"] == 0
    assert summary["meanCoverageRatio"] is None
    assert summary["missingFieldCounts"] == {}


def test_reliability_report_includes_expected_field_coverage_summary() -> None:
    report = build_phase85_reliability_report(
        run_id="run-expected-coverage",
        title_prefix="Phase 8.5",
        documents=[
            _document_with_extractions(
                [
                    _region_extraction(
                        {
                            "expected": ["total_amount"],
                            "produced": ["receipt.transaction.total"],
                            "missing": [],
                            "coverage_ratio": 1.0,
                        }
                    )
                ]
            )
        ],
    )

    coverage = report["expectedFieldCoverage"]
    assert coverage["regionsWithExpectedFields"] == 1
    assert coverage["fullyCoveredRegionCount"] == 1
    assert coverage["missingExpectedFieldCount"] == 0
