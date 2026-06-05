from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_report_normalization import (
    all_rows,
    dict_value,
    fingerprint,
    get_value,
    json_safe,
    list_value,
    normalized_token,
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
            _stable_rows(
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
            )
        ),
        "semanticRegions": fingerprint(
            _stable_rows(
                select_values(
                    row,
                    (
                        "page_number",
                        "semantic_type",
                        "granite_task",
                        "target_schema",
                        "grounding_kind",
                    ),
                )
                for row in _selected_semantic_region_rows(documents)
            )
        ),
        "plannerTasks": fingerprint(
            _stable_rows(
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
                for row in _selected_planner_task_rows(documents)
            )
        ),
        "candidateFingerprints": fingerprint(candidate_fingerprints),
        "canonicalOutput": fingerprint(
            {
                "fields": _stable_rows(all_rows(documents, "fields")),
                "lineItems": _stable_rows(all_rows(documents, "lineItems")),
                "observations": _stable_rows(all_rows(documents, "observations")),
            }
        ),
        "reviewTasks": fingerprint(
            _stable_rows(
                select_values(row, ("task_type", "status", "reason", "priority"))
                for row in all_rows(documents, "reviewTasks")
                if _is_model_runtime_review_task(row)
            )
        ),
        "rejectionDistribution": fingerprint(admission_summary.get("rejectionReasons", {})),
    }


def _stable_rows(rows: Any) -> list[Any]:
    return sorted((json_safe(row) for row in rows), key=fingerprint)


def _selected_semantic_region_rows(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for document in documents:
        regions = [
            row
            for row in list_value(get_value(document, "semanticRegions"))
            if isinstance(row, dict)
        ]
        selected_region_ids = {
            str(region_id)
            for task in _planner_task_rows(document)
            if _is_selected_planner_task(task)
            if (region_id := get_value(task, "semantic_region_id", "semanticRegionId"))
            not in (None, "")
        }
        if not selected_region_ids:
            rows.extend(regions)
            continue
        rows.extend(
            row
            for row in regions
            if str(get_value(row, "semantic_region_id", "semanticRegionId") or "")
            in selected_region_ids
        )
    return rows


def _selected_planner_task_rows(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for document in documents
        for row in _planner_task_rows(document)
        if _is_selected_planner_task(row)
    ]


def _planner_task_rows(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in list_value(get_value(document, "plannerTasks")) if isinstance(row, dict)]


def _is_selected_planner_task(row: dict[str, Any]) -> bool:
    return normalized_token(get_value(row, "status")) == "selected"


def _is_model_runtime_review_task(row: dict[str, Any]) -> bool:
    task_type = str(get_value(row, "task_type", "taskType") or "").strip().lower()
    return task_type != "relationship_suggestion"
