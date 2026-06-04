from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from lib.semantic_annotations.models import SemanticRegionAnnotation
from lib.semantic_annotations.schema_fit import SchemaFitDecision

LINE_ITEM_SEMANTIC_TYPES = {
    "covered_services_line_item_table",
    "invoice_line_item_table",
    "receipt_line_item_table",
    "retail_order_line_item_table",
    "service_record_line_item_table",
    "dispute_transaction_table",
}
SUMMARY_SEMANTIC_TYPES = {
    "billing_summary",
    "payment_summary",
    "patient_responsibility_summary",
    "receipt_payment_summary",
    "escrow_summary",
    "mortgage_payment_summary",
}
DOCLING_REGION_SOURCE = "docling_structural"


@dataclass(frozen=True)
class GraniteJobSpec:
    region: SemanticRegionAnnotation
    region_id: UUID
    target_schema: str
    canonical_target_schema: str
    model_output_schema_name: str
    contract_resolution_reason: str
    compatibility_mode: str | None
    extractor_backend: str
    priority: int
    ordinal: int
    schema_fit: SchemaFitDecision
    metadata: dict[str, object]


@dataclass(frozen=True)
class GraniteExtractionPlan:
    selected: tuple[GraniteJobSpec, ...]
    dropped: tuple[GraniteJobSpec, ...]
    warnings: tuple[str, ...]
    bucket_counts: dict[str, int]
    max_tasks_per_document: int = 0
    max_tasks_per_page: int = 0

    def to_metadata(self) -> dict[str, object]:
        selected_by_backend: dict[str, int] = defaultdict(int)
        selected_by_bucket: dict[str, int] = defaultdict(int)
        selected_by_page: dict[str, int] = defaultdict(int)
        for spec in self.selected:
            selected_by_backend[spec.extractor_backend] += 1
            selected_by_bucket[_bucket(spec)] += 1
            selected_by_page[_page_key(spec)] += 1
        return {
            "selectedCount": len(self.selected),
            "droppedCount": len(self.dropped),
            "plannedTaskCount": len(self.selected) + len(self.dropped),
            "maxTasksPerDocumentPolicy": self.max_tasks_per_document,
            "maxTasksPerPagePolicy": self.max_tasks_per_page,
            "safeSkipCount": len(self.dropped),
            "safeAbstentionCount": 0,
            "unsafeFailureCount": 0,
            "bucketCounts": dict(self.bucket_counts),
            "selectedTaskCountByBackend": dict(selected_by_backend),
            "selectedTaskCountByBucket": dict(selected_by_bucket),
            "selectedTaskCountByPage": dict(selected_by_page),
            "warnings": list(self.warnings),
            "selected": [_spec_summary(spec) for spec in self.selected],
            "dropped": [_spec_summary(spec) for spec in self.dropped[:12]],
        }


def plan_granite_jobs(
    specs: list[GraniteJobSpec],
    *,
    quality_mode: str,
) -> GraniteExtractionPlan:
    selectable_specs, invalid_specs, invalid_warnings = _partition_selectable_specs(specs)
    deduped = _dedupe_specs(selectable_specs)
    buckets: dict[str, list[GraniteJobSpec]] = defaultdict(list)
    for spec in deduped:
        buckets[_bucket(spec)].append(spec)
    for bucket_specs in buckets.values():
        bucket_specs.sort(key=_sort_key)

    hard_limit = {
        "smart": 6,
        "high_quality": 8,
        "rescue": 1,
    }.get(quality_mode, 6)
    per_page_limit = {
        "smart": 3,
        "high_quality": 4,
        "rescue": 1,
    }.get(quality_mode, 3)
    bucket_limits = {
        "line_item": 4,
        "docling_table": 3,
        "observation_primary": 2,
        "summary": 2,
        "other": 2,
    }

    selected: list[GraniteJobSpec] = []
    selected_by_page: dict[str, int] = defaultdict(int)
    warnings: list[str] = list(invalid_warnings)

    def select_if_allowed(spec: GraniteJobSpec) -> bool:
        page_key = _page_key(spec)
        if selected_by_page[page_key] >= per_page_limit:
            warnings.append(f"granite_plan_page_limit_reached:{page_key}")
            return False
        selected.append(spec)
        selected_by_page[page_key] += 1
        return True

    for bucket in (
        "line_item",
        "docling_table",
        "observation_primary",
        "summary",
        "other",
    ):
        for spec in buckets.get(bucket, [])[: bucket_limits[bucket]]:
            if len(selected) >= hard_limit:
                warnings.append(f"granite_plan_hard_limit_reached_before_{bucket}")
                break
            select_if_allowed(spec)

    selected_ids = {id(spec) for spec in selected}
    if len(selected) < hard_limit:
        remaining = sorted(
            (spec for spec in deduped if id(spec) not in selected_ids),
            key=_sort_key,
        )
        for spec in remaining:
            if len(selected) >= hard_limit:
                break
            if select_if_allowed(spec):
                selected_ids.add(id(spec))
    dropped = (*invalid_specs, *(spec for spec in deduped if id(spec) not in selected_ids))
    for spec in dropped:
        must_extract_reason = spec.region.metadata.get("must_extract_reason")
        if must_extract_reason:
            warnings.append(
                f"dropped_must_extract_target:{spec.region.semantic_type}:{must_extract_reason}"
            )

    plan = GraniteExtractionPlan(
        selected=tuple(selected),
        dropped=dropped,
        warnings=tuple(dict.fromkeys(warnings)),
        bucket_counts={bucket: len(bucket_specs) for bucket, bucket_specs in buckets.items()},
        max_tasks_per_document=hard_limit,
        max_tasks_per_page=per_page_limit,
    )
    return _attach_plan_metadata(plan)


def _partition_selectable_specs(
    specs: list[GraniteJobSpec],
) -> tuple[list[GraniteJobSpec], tuple[GraniteJobSpec, ...], tuple[str, ...]]:
    selectable: list[GraniteJobSpec] = []
    dropped: list[GraniteJobSpec] = []
    warnings: list[str] = []
    for spec in specs:
        reason = _selected_spec_violation(spec)
        if reason is None:
            selectable.append(spec)
            continue
        dropped.append(spec)
        warnings.append(f"granite_plan_{reason}:{spec.region_id}")
    return selectable, tuple(dropped), tuple(dict.fromkeys(warnings))


def _selected_spec_violation(spec: GraniteJobSpec) -> str | None:
    if not str(spec.model_output_schema_name or "").strip():
        return "missing_contract"
    if not _has_concrete_grounding(spec):
        return "missing_grounding"
    if _has_incompatible_contract(spec):
        return "incompatible_schema"
    return None


def _has_concrete_grounding(spec: GraniteJobSpec) -> bool:
    grounding = spec.region.grounding
    if grounding.kind == "page":
        return grounding.page_id is not None
    if grounding.kind == "element":
        return grounding.element_id is not None
    if grounding.kind == "table":
        return grounding.table_id is not None
    return False


def _has_incompatible_contract(spec: GraniteJobSpec) -> bool:
    compatibility_mode = _normalized_taxonomy(spec.compatibility_mode)
    contract_reason = _normalized_taxonomy(spec.contract_resolution_reason)
    if compatibility_mode in {
        "missing",
        "incompatible",
        "incompatible_family",
        "incompatible_schema",
        "incompatible_family_schema",
    }:
        return True
    return "incompatible" in contract_reason or "missing_contract" in contract_reason


def _normalized_taxonomy(value: object) -> str:
    text = str(value or "").strip().replace("-", "_").replace(" ", "_")
    return "_".join(part for part in text.lower().split("_") if part)


def _attach_plan_metadata(plan: GraniteExtractionPlan) -> GraniteExtractionPlan:
    report = plan.to_metadata()
    selected = tuple(
        replace(
            spec,
            metadata={
                **spec.metadata,
                "granite_extraction_plan": report,
                "granite_extraction_bucket": _bucket(spec),
            },
        )
        for spec in plan.selected
    )
    return replace(plan, selected=selected)


def _bucket(spec: GraniteJobSpec) -> str:
    region = spec.region
    metadata = region.metadata
    if region.semantic_type in LINE_ITEM_SEMANTIC_TYPES:
        return "line_item"
    if metadata.get("region_source") == DOCLING_REGION_SOURCE and region.grounding.table_id:
        return "docling_table"
    if spec.target_schema == "document_observation" and metadata.get("coverage_role") == "primary":
        return "observation_primary"
    if region.semantic_type in SUMMARY_SEMANTIC_TYPES:
        return "summary"
    return "other"


def _sort_key(spec: GraniteJobSpec) -> tuple[object, ...]:
    confidence = spec.region.confidence if spec.region.confidence is not None else 0.0
    return (spec.priority, _source_rank(spec), -confidence, spec.ordinal)


def _source_rank(spec: GraniteJobSpec) -> int:
    metadata = spec.region.metadata
    if metadata.get("must_extract_reason"):
        return 0
    if metadata.get("region_source") == DOCLING_REGION_SOURCE:
        return 1
    return 2


def _dedupe_specs(specs: list[GraniteJobSpec]) -> list[GraniteJobSpec]:
    best: dict[tuple[Any, ...], GraniteJobSpec] = {}
    for spec in specs:
        key = _dedupe_key(spec)
        current = best.get(key)
        if current is None or _sort_key(spec) < _sort_key(current):
            best[key] = spec
    return list(best.values())


def _dedupe_key(spec: GraniteJobSpec) -> tuple[Any, ...]:
    grounding = spec.region.grounding
    page_level_intent: tuple[str, ...] = ()
    if grounding.element_id is None and grounding.table_id is None:
        page_level_intent = tuple(spec.region.expected_fields)
    return (
        spec.target_schema,
        spec.region.semantic_type,
        spec.region.granite_task,
        spec.region.metadata.get("region_source"),
        spec.region.metadata.get("coverage_role"),
        grounding.kind,
        grounding.page_id,
        grounding.element_id,
        grounding.table_id,
        page_level_intent,
    )


def _page_key(spec: GraniteJobSpec) -> str:
    grounding = spec.region.grounding
    if grounding.page_id is not None:
        return str(grounding.page_id)
    for metadata_key in ("page_id", "pageId", "page_number", "pageNumber"):
        value = spec.region.metadata.get(metadata_key)
        if value is not None:
            return str(value)
    return "unknown"


def _spec_summary(spec: GraniteJobSpec) -> dict[str, object]:
    return {
        "regionId": str(spec.region_id),
        "pageKey": _page_key(spec),
        "semanticType": spec.region.semantic_type,
        "targetSchema": spec.target_schema,
        "canonicalTargetSchema": spec.canonical_target_schema,
        "modelOutputSchemaName": spec.model_output_schema_name,
        "contractResolutionReason": spec.contract_resolution_reason,
        "compatibilityMode": spec.compatibility_mode,
        "extractorBackend": spec.extractor_backend,
        "graniteTask": spec.region.granite_task,
        "bucket": _bucket(spec),
        "schemaFitReason": spec.schema_fit.reason,
        "mustExtractReason": spec.region.metadata.get("must_extract_reason"),
        "regionSource": spec.region.metadata.get("region_source"),
    }
