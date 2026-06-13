from __future__ import annotations

from typing import Any

from lib.model_runtime.reliability_report_normalization import (
    all_rows,
    bool_value,
    dict_value,
    get_value,
    int_value,
    list_value,
    snake,
)
from lib.model_runtime.source_engines import (
    is_model_source_engine,
    is_non_model_source_engine,
)

ViolationMap = dict[str, list[dict[str, Any]]]

_ACCEPTED_STATUSES = {"auto_accepted", "user_confirmed", "user_corrected", "accepted"}
_REQUIRED_FIELD_HINTS = {
    "invoice.invoice_number",
    "invoice.issued_date",
    "invoice.total_amount",
    "medical_eob.claim_number",
    "medical_eob.patient_name",
    "receipt.receipt_date",
    "receipt.total_amount",
}
_MERCHANT_SELLER_HINTS = ("merchant", "seller", "counterparty")


def evaluate_planner_tasks(documents: list[dict[str, Any]], violations: ViolationMap) -> None:
    region_by_id = _semantic_regions_by_id(documents)
    for task in all_rows(documents, "plannerTasks"):
        if not _is_selected_or_enqueued_task(task) or not _is_granite_semantic_region_task(task):
            continue
        if not _normalized_text(
            get_value(task, "model_output_schema_name", "modelOutputSchemaName")
        ):
            _add_violation(
                violations,
                "selectedGraniteTasksMissingContract",
                task,
                "missing_model_output_schema_name",
            )
        if not _has_concrete_grounding(task, region_by_id):
            _add_violation(
                violations,
                "selectedGraniteTasksMissingGrounding",
                task,
                "missing_concrete_grounding",
            )
        if _has_incompatible_schema(task):
            _add_violation(
                violations,
                "selectedGraniteTasksIncompatibleFamilySchema",
                task,
                "incompatible_schema_or_contract_resolution",
            )


def evaluate_semantic_annotations(
    documents: list[dict[str, Any]],
    violations: ViolationMap,
) -> None:
    for doc in documents:
        document = dict_value(get_value(doc, "document"))
        for semantic in list_value(get_value(doc, "semantic")):
            if not isinstance(semantic, dict):
                continue
            if not _requires_deterministic_baseline_telemetry(semantic):
                continue
            telemetry = dict_value(
                get_value(semantic, "deterministic_baseline", "deterministicBaseline")
            )
            if not telemetry:
                _add_violation(
                    violations,
                    "semanticAnnotationsMissingDeterministicBaseline",
                    semantic,
                    "missing_deterministic_baseline_telemetry",
                    document=document,
                )
                continue
            if _deterministic_baseline_coverage_regressed(telemetry):
                _add_violation(
                    violations,
                    "semanticAnnotationsMissingDeterministicBaseline",
                    semantic,
                    "deterministic_baseline_coverage_regressed",
                    document=document,
                )


def evaluate_extractions(documents: list[dict[str, Any]], violations: ViolationMap) -> None:
    for doc in documents:
        extraction_rows = _extraction_rows(doc)
        for extraction in extraction_rows:
            if _is_auto_accepted_model_semantic_region_extraction(extraction):
                _add_violation(
                    violations,
                    "modelBackedSemanticRegionAutoAccepted",
                    extraction,
                    "model_backed_semantic_region_auto_accepted",
                )
            if _is_incompatible_aggregate_extraction(extraction):
                _add_violation(
                    violations,
                    "aggregateSchemasFromIncompatibleFamilies",
                    extraction,
                    "aggregate_schema_from_incompatible_source_family",
                )
            if _is_current_aggregate_extraction(extraction) and _aggregate_lineage_missing(
                extraction
            ):
                _add_violation(
                    violations,
                    "aggregateExtractionsMissingRunLineage",
                    extraction,
                    "missing_aggregate_run_lineage",
                    document=dict_value(get_value(doc, "document")),
                )
        _evaluate_duplicate_current_aggregates(doc, extraction_rows, violations)


def evaluate_canonical_fields(documents: list[dict[str, Any]], violations: ViolationMap) -> None:
    for doc in documents:
        document = dict_value(get_value(doc, "document"))
        for field in _canonical_field_rows(doc):
            if not _is_accepted_field(field):
                continue
            field_path = _normalized_field_path(get_value(field, "field_path", "fieldPath"))
            if _is_fabricated_required_field(field, field_path):
                _add_violation(
                    violations,
                    "fabricatedCanonicalRequiredFields",
                    field,
                    "fabricated_required_field",
                    document=document,
                )
            if _is_title_derived_merchant_or_seller(field, field_path, document):
                _add_violation(
                    violations,
                    "titleDerivedMerchantSellerWithoutAllowlist",
                    field,
                    "title_derived_merchant_seller_without_allowlist",
                    document=document,
                )


def _canonical_field_rows(doc: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("fields", "canonicalFields", "canonical_fields"):
        rows.extend(row for row in list_value(get_value(doc, key)) if isinstance(row, dict))
    return rows


def _extraction_rows(doc: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("extractions", "semanticRegionExtractions"):
        rows.extend(row for row in list_value(get_value(doc, key)) if isinstance(row, dict))
    return rows


def _requires_deterministic_baseline_telemetry(semantic: dict[str, Any]) -> bool:
    source_engine = _normalized_text(get_value(semantic, "source_engine", "sourceEngine"))
    return source_engine in {"qwen3_vl_8b", "docling"}


def _deterministic_baseline_coverage_regressed(telemetry: dict[str, Any]) -> bool:
    if bool_value(get_value(telemetry, "qwen_annotation_failed", "qwenAnnotationFailed")):
        return False
    baseline_region_count = get_value(
        telemetry,
        "baseline_region_count",
        "baselineRegionCount",
    )
    plan_region_count = get_value(telemetry, "plan_region_count", "planRegionCount")
    if baseline_region_count in (None, "") or plan_region_count in (None, ""):
        return True
    return int_value(plan_region_count) < int_value(baseline_region_count)


def _evaluate_duplicate_current_aggregates(
    doc: dict[str, Any],
    extraction_rows: list[dict[str, Any]],
    violations: ViolationMap,
) -> None:
    current_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for extraction in extraction_rows:
        if not _is_current_aggregate_extraction(extraction):
            continue
        schema_name = _normalized_schema_family(get_value(extraction, "schema_name", "schemaName"))
        if not schema_name:
            continue
        current_by_key.setdefault((schema_name, "aggregate"), []).append(extraction)
    document = dict_value(get_value(doc, "document"))
    for schema_scope, rows in sorted(current_by_key.items()):
        if len(rows) <= 1:
            continue
        schema_name, scope = schema_scope
        _add_violation(
            violations,
            "duplicateCurrentAggregateExtractions",
            {"id": f"{schema_name}:{scope}"},
            "duplicate_current_aggregate_extraction",
            document=document,
        )


def _is_current_aggregate_extraction(extraction: dict[str, Any]) -> bool:
    scope = _normalized_text(get_value(extraction, "extraction_scope", "extractionScope"))
    return scope == "aggregate" and bool_value(get_value(extraction, "is_current", "isCurrent"))


def _aggregate_lineage_missing(extraction: dict[str, Any]) -> bool:
    normalization = dict_value(
        get_value(extraction, "normalization_json", "normalizationJson", "normalization")
    )
    metadata = dict_value(get_value(extraction, "metadata_json", "metadataJson", "metadata"))
    run_id = get_value(normalization, "run_id", "runId") or get_value(metadata, "run_id", "runId")
    source_run_ids = list_value(
        get_value(normalization, "source_run_ids", "sourceRunIds")
    ) or list_value(get_value(metadata, "source_run_ids", "sourceRunIds"))
    region_extraction_ids = list_value(
        get_value(normalization, "regionExtractionIds", "region_extraction_ids")
    ) or list_value(get_value(metadata, "regionExtractionIds", "region_extraction_ids"))
    return not (run_id and source_run_ids and region_extraction_ids)


def _semantic_regions_by_id(documents: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    regions: dict[str, dict[str, Any]] = {}
    for region in all_rows(documents, "semanticRegions"):
        region_id = get_value(region, "semantic_region_id", "semanticRegionId", "id")
        if region_id:
            regions[str(region_id)] = region
    return regions


def _is_selected_or_enqueued_task(task: dict[str, Any]) -> bool:
    status = _normalized_text(get_value(task, "status"))
    return status.startswith("selected") or status in {
        "enqueued",
        "queued",
        "running",
        "completed",
        "succeeded",
    }


def _is_granite_semantic_region_task(task: dict[str, Any]) -> bool:
    backend = _normalized_text(get_value(task, "extractor_backend", "extractorBackend"))
    semantic_region_id = get_value(task, "semantic_region_id", "semanticRegionId")
    return "granite" in backend and semantic_region_id not in (None, "")


def _has_concrete_grounding(
    task: dict[str, Any],
    region_by_id: dict[str, dict[str, Any]],
) -> bool:
    task_json = dict_value(get_value(task, "task_json", "taskJson"))
    grounding = dict_value(get_value(task_json, "grounding"))
    region_id = get_value(task, "semantic_region_id", "semanticRegionId")
    region = region_by_id.get(str(region_id)) if region_id else None
    region_grounding = dict_value(get_value(region or {}, "grounding"))

    kind = _normalized_text(
        get_value(
            task,
            "grounding_kind",
            "groundingKind",
        )
        or get_value(grounding, "kind")
        or get_value(region_grounding, "kind")
        or ""
    )
    page_value = (
        get_value(task, "page_number", "pageNumber")
        or get_value(grounding, "page_number", "pageNumber", "page_id", "pageId")
        or get_value(region_grounding, "page_number", "pageNumber", "page_id", "pageId")
    )
    table_value = (
        get_value(task, "table_id", "tableId", "docling_table_id", "doclingTableId")
        or get_value(grounding, "table_id", "tableId", "docling_table_id", "doclingTableId")
        or get_value(
            region_grounding,
            "table_id",
            "tableId",
            "docling_table_id",
            "doclingTableId",
        )
    )
    element_value = (
        get_value(task, "element_id", "elementId")
        or get_value(grounding, "element_id", "elementId")
        or get_value(region_grounding, "element_id", "elementId")
    )
    bbox_value = get_value(grounding, "bbox") or get_value(region_grounding, "bbox")

    if kind in {"table", "docling_table"}:
        return _has_grounding_value(table_value) and _has_grounding_value(page_value)
    if kind in {"element", "text_element"}:
        return _has_grounding_value(element_value) and _has_grounding_value(page_value)
    if kind in {"page", "full_page", "region", "visual_region"}:
        return _has_grounding_value(page_value) or _has_grounding_value(bbox_value)
    return any(
        _has_grounding_value(value)
        for value in (
            page_value,
            table_value,
            element_value,
            bbox_value,
        )
    )


def _has_grounding_value(value: Any) -> bool:
    if value in (None, ""):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict | list | tuple | set):
        return bool(value)
    return True


def _has_incompatible_schema(task: dict[str, Any]) -> bool:
    compatibility_mode = _normalized_taxonomy_label(
        get_value(task, "compatibility_mode", "compatibilityMode")
    )
    contract_reason = _normalized_taxonomy_label(
        get_value(task, "contract_resolution_reason", "contractResolutionReason")
    )
    if compatibility_mode in {
        "missing",
        "incompatible",
        "incompatible_family",
        "incompatible_schema",
        "incompatible_family_schema",
    }:
        return True
    return "incompatible" in contract_reason or "missing_contract" in contract_reason


def _normalized_taxonomy_label(value: Any) -> str:
    return _normalized_path_segment(value)


def _is_auto_accepted_model_semantic_region_extraction(extraction: dict[str, Any]) -> bool:
    scope = _normalized_text(get_value(extraction, "extraction_scope", "extractionScope"))
    region_id = get_value(
        extraction,
        "source_semantic_region_id",
        "sourceSemanticRegionId",
        "semantic_region_id",
        "semanticRegionId",
    )
    review_status = _normalized_text(get_value(extraction, "review_status", "reviewStatus"))
    return (
        review_status == "auto_accepted"
        and (scope == "semantic_region" or region_id not in (None, ""))
        and _is_model_backed_extraction(extraction)
    )


def _is_model_backed_extraction(extraction: dict[str, Any]) -> bool:
    source_engine = get_value(extraction, "source_engine", "sourceEngine")
    if is_model_source_engine(source_engine):
        return True
    if is_non_model_source_engine(source_engine):
        return False
    return bool(
        get_value(
            extraction,
            "model_name",
            "modelName",
            "modelOutputSchemaName",
            "model_output_schema_name",
        )
    )


def _is_incompatible_aggregate_extraction(extraction: dict[str, Any]) -> bool:
    scope = _normalized_text(get_value(extraction, "extraction_scope", "extractionScope"))
    if scope not in {"aggregate", "document"}:
        return False
    schema_name = _normalized_schema_family(get_value(extraction, "schema_name", "schemaName"))
    if schema_name in {"", "document_observation"}:
        return False
    validation = dict_value(
        get_value(extraction, "validation_json", "validationJson", "validation")
    )
    normalization = dict_value(
        get_value(extraction, "normalization_json", "normalizationJson", "normalization")
    )
    warnings = [
        str(item)
        for item in [
            *list_value(get_value(validation, "warnings", "reviewWarnings")),
            *list_value(get_value(normalization, "warnings", "reviewWarnings")),
        ]
    ]
    if any("incompatible" in warning.lower() for warning in warnings):
        return True
    source_families = set(
        filter(
            None,
            (
                _normalized_schema_family(item)
                for item in list_value(
                    get_value(normalization, "sourceFamilies", "source_families")
                )
            ),
        )
    )
    return bool(source_families) and schema_name not in source_families


def _is_accepted_field(field: dict[str, Any]) -> bool:
    status = _normalized_text(get_value(field, "review_status", "reviewStatus", "status"))
    return status in _ACCEPTED_STATUSES


def _is_fabricated_required_field(field: dict[str, Any], field_path: str) -> bool:
    if not _is_required_field(field_path):
        return False
    validation = dict_value(get_value(field, "validation_json", "validationJson", "validation"))
    metadata = dict_value(get_value(field, "metadata_json", "metadataJson", "metadata"))
    evidence = list_value(get_value(field, "evidence", "evidence_json", "evidenceJson"))
    source_kind = str(get_value(field, "source_kind", "sourceKind") or "").lower()
    return (
        bool_value(get_value(validation, "fabricated", "isFabricated"))
        or bool_value(get_value(metadata, "fabricated", "isFabricated"))
        or "fabricated" in source_kind
        or not evidence
    )


def _is_required_field(field_path: str) -> bool:
    if field_path in _REQUIRED_FIELD_HINTS:
        return True
    return any(field_path.endswith(f".{suffix}") for suffix in ("invoice_number", "total_amount"))


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalized_field_path(value: Any) -> str:
    return ".".join(
        _normalized_path_segment(segment)
        for segment in str(value or "").split(".")
        if segment.strip()
    )


def _normalized_path_segment(value: Any) -> str:
    segment = snake(str(value or "").strip()).replace("-", "_").replace(" ", "_").lower()
    return "_".join(part for part in segment.split("_") if part)


def _normalized_schema_family(value: Any) -> str:
    return _normalized_path_segment(value)


def _is_title_derived_merchant_or_seller(
    field: dict[str, Any],
    field_path: str,
    document: dict[str, Any],
) -> bool:
    if not any(hint in field_path for hint in _MERCHANT_SELLER_HINTS):
        return False
    if _title_derivation_allowed(field) or _title_derivation_allowed(document):
        return False
    if _source_is_document_title(field):
        return True
    evidence = list_value(get_value(field, "evidence", "evidence_json", "evidenceJson"))
    return any(_evidence_is_document_title(item) for item in evidence if isinstance(item, dict))


def _title_derivation_allowed(mapping: dict[str, Any]) -> bool:
    metadata = dict_value(get_value(mapping, "metadata", "metadata_json", "metadataJson"))
    return bool_value(
        get_value(
            mapping,
            "allow_title_derived_merchant_seller",
            "allowTitleDerivedMerchantSeller",
        )
    ) or bool_value(
        get_value(
            metadata,
            "allow_title_derived_merchant_seller",
            "allowTitleDerivedMerchantSeller",
        )
    )


def _evidence_is_document_title(evidence: dict[str, Any]) -> bool:
    return _source_is_document_title(evidence)


def _source_is_document_title(mapping: dict[str, Any]) -> bool:
    source = _normalized_path_segment(
        get_value(mapping, "source", "sourceKind", "source_kind", "sourceEngine", "source_engine")
        or ""
    )
    return source in {"document_title", "title"} or "document_title" in source


def _add_violation(
    violations: ViolationMap,
    key: str,
    row: dict[str, Any],
    reason: str,
    *,
    document: dict[str, Any] | None = None,
) -> None:
    source = document or row
    violations[key].append(
        {
            "reason": reason,
            "documentId": get_value(source, "document_id", "documentId", "id"),
            "entityId": get_value(
                row,
                "id",
                "plan_task_id",
                "planTaskId",
                "candidate_fingerprint",
                "candidateFingerprint",
                "field_path",
                "fieldPath",
            ),
        }
    )
