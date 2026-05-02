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

    def to_metadata(self) -> dict[str, object]:
        selected_by_backend: dict[str, int] = defaultdict(int)
        selected_by_bucket: dict[str, int] = defaultdict(int)
        for spec in self.selected:
            selected_by_backend[spec.extractor_backend] += 1
            selected_by_bucket[_bucket(spec)] += 1
        return {
            "selectedCount": len(self.selected),
            "droppedCount": len(self.dropped),
            "plannedTaskCount": len(self.selected) + len(self.dropped),
            "safeSkipCount": len(self.dropped),
            "safeAbstentionCount": 0,
            "unsafeFailureCount": 0,
            "bucketCounts": dict(self.bucket_counts),
            "selectedTaskCountByBackend": dict(selected_by_backend),
            "selectedTaskCountByBucket": dict(selected_by_bucket),
            "warnings": list(self.warnings),
            "selected": [_spec_summary(spec) for spec in self.selected],
            "dropped": [_spec_summary(spec) for spec in self.dropped[:12]],
        }


def plan_granite_jobs(
    specs: list[GraniteJobSpec],
    *,
    quality_mode: str,
) -> GraniteExtractionPlan:
    deduped = _dedupe_specs(specs)
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
    bucket_limits = {
        "line_item": 4,
        "docling_table": 3,
        "observation_primary": 2,
        "summary": 2,
        "other": 2,
    }

    selected: list[GraniteJobSpec] = []
    warnings: list[str] = []
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
            selected.append(spec)

    selected_ids = {id(spec) for spec in selected}
    if len(selected) < hard_limit:
        remaining = sorted(
            (spec for spec in deduped if id(spec) not in selected_ids),
            key=_sort_key,
        )
        for spec in remaining:
            if len(selected) >= hard_limit:
                break
            selected.append(spec)
            selected_ids.add(id(spec))
    dropped = tuple(spec for spec in deduped if id(spec) not in selected_ids)
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
    )
    return _attach_plan_metadata(plan)


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


def _spec_summary(spec: GraniteJobSpec) -> dict[str, object]:
    return {
        "regionId": str(spec.region_id),
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
