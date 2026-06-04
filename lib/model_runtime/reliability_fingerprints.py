from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_report_normalization import (
    all_rows,
    dict_value,
    fingerprint,
    get_value,
    select_values,
)


def repeatability_fingerprints(
    documents: list[dict[str, Any]],
    admission_summary: dict[str, Any],
) -> dict[str, str]:
    candidate_fingerprints = sorted(
        str(get_value(event, "candidate_fingerprint", "candidateFingerprint"))
        for event in all_rows(documents, "admissionEvents")
        if get_value(event, "candidate_fingerprint", "candidateFingerprint")
    )
    return {
        "documentFamily": fingerprint(
            [
                {
                    "family": get_value(
                        dict_value(get_value(doc, "document")),
                        "document_family",
                        "documentFamily",
                    ),
                    "reviewStatus": get_value(
                        dict_value(get_value(doc, "document")),
                        "review_status",
                        "reviewStatus",
                    ),
                }
                for doc in documents
            ]
        ),
        "semanticRegions": fingerprint(
            [
                select_values(
                    row,
                    (
                        "page_number",
                        "semantic_type",
                        "granite_task",
                        "target_schema",
                        "grounding_kind",
                        "review_required",
                    ),
                )
                for row in all_rows(documents, "semanticRegions")
            ]
        ),
        "plannerTasks": fingerprint(
            [
                select_values(
                    row,
                    (
                        "status",
                        "semantic_type",
                        "extractor_backend",
                        "target_schema",
                        "canonical_target_schema",
                        "model_output_schema_name",
                        "compatibility_mode",
                        "page_number",
                    ),
                )
                for row in all_rows(documents, "plannerTasks")
            ]
        ),
        "candidateFingerprints": fingerprint(candidate_fingerprints),
        "canonicalOutput": fingerprint(
            {
                "fields": all_rows(documents, "fields"),
                "lineItems": all_rows(documents, "lineItems"),
                "observations": all_rows(documents, "observations"),
            }
        ),
        "reviewTasks": fingerprint(
            [
                select_values(row, ("task_type", "status", "reason", "priority"))
                for row in all_rows(documents, "reviewTasks")
            ]
        ),
        "rejectionDistribution": fingerprint(admission_summary.get("rejectionReasons", {})),
    }
