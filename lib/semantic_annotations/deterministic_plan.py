"""Deterministic-primary planning (ADR 0006 X4, migration phase E3).

The Docling-derived structural plan is the plan: tables become line-item
lane targets and anchored observation families become KVP targets through
the existing docling_targets builders, with no model in the loop. Qwen's
manifest augments that baseline (semantic labels, extra regions, page
roles); it may never reduce coverage, and a Qwen failure degrades the
document to the deterministic baseline instead of stranding it.

The baseline fingerprint hashes run-stable structure (semantic types,
granite tasks, table page/index positions, expected fields) — never
per-run UUIDs — so two ingests of the same document produce the same
fingerprint for the repeatability gate.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any

from lib.extraction.models import ExtractionSourceDocument
from lib.semantic_annotations.docling_targets import (
    augment_manifest_with_docling_structural_targets,
)
from lib.semantic_annotations.manifest_merge import page_manifest_json, region_manifest_json
from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    PageSemanticAnnotation,
    QualityMode,
    SemanticAnnotationResult,
    SemanticRegionAnnotation,
)

DETERMINISTIC_PLANNER_VERSION = "phase8_5-deterministic-baseline-v1"


def deterministic_baseline_manifest(
    source: ExtractionSourceDocument,
    *,
    quality_mode: QualityMode = "smart",
) -> DocumentSemanticManifest:
    """Build the model-free structural plan from Docling parse state."""
    pages = [
        PageSemanticAnnotation(
            page_id=page.page_id,
            page_number=page.page_number,
            page_role="content",
            extraction_usefulness="unknown",
            reason="deterministic_baseline",
        )
        for page in source.pages
    ]
    empty = DocumentSemanticManifest(
        document_id=source.document_id,
        household_id=source.household_id,
        quality_mode=quality_mode,
        profile_name="deterministic-planner",
        source_engine="docling_baseline",
        model_name="deterministic-planner",
        model_version="e3-v1",
        prompt_version=DETERMINISTIC_PLANNER_VERSION,
        pages=pages,
        regions=[],
        confidence={"planner": DETERMINISTIC_PLANNER_VERSION},
        manifest={
            "document_type": None,
            "planner": DETERMINISTIC_PLANNER_VERSION,
            "pages": [page_manifest_json(page) for page in pages],
            "regions": [],
        },
    )
    return augment_manifest_with_docling_structural_targets(source, empty)


def baseline_plan_fingerprint(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
) -> str:
    """Run-stable identity for the deterministic baseline plan."""
    page_numbers = {str(page.page_id): page.page_number for page in source.pages}
    entries = sorted(_region_identity(region, page_numbers) for region in manifest.regions)
    payload = json.dumps(entries, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def apply_baseline_invariant(
    source: ExtractionSourceDocument,
    baseline: DocumentSemanticManifest,
    result: SemanticAnnotationResult,
) -> SemanticAnnotationResult:
    """Enforce plan ⊇ deterministic baseline and record plan-identity telemetry.

    The docling structural augmentation already unions uncovered targets into
    the plan; what can still drop a baseline region is its additions cap.
    Any baseline region whose structural target is absent from the final
    plan is appended here, so coverage is enforced rather than asserted.
    """
    manifest = result.manifest
    uncovered = [
        region
        for region in baseline.regions
        if not _baseline_region_covered(region, manifest.regions)
    ]
    regions = list(manifest.regions)
    if uncovered:
        regions = [*regions, *uncovered]
    telemetry = {
        "version": DETERMINISTIC_PLANNER_VERSION,
        "fingerprint": baseline_plan_fingerprint(source, baseline),
        "baseline_region_count": len(baseline.regions),
        "enforced_region_count": len(uncovered),
        "plan_region_count": len(regions),
    }
    manifest_payload = dict(manifest.manifest)
    manifest_payload["deterministic_baseline"] = telemetry
    if uncovered:
        manifest_payload["regions"] = [region_manifest_json(region) for region in regions]
    confidence = dict(manifest.confidence)
    confidence["deterministic_baseline"] = telemetry
    updated = replace(
        manifest,
        regions=regions,
        confidence=confidence,
        manifest=manifest_payload,
    )
    return replace(result, manifest=updated)


def baseline_only_result(
    source: ExtractionSourceDocument,
    baseline: DocumentSemanticManifest,
    *,
    failure_reason: str,
) -> SemanticAnnotationResult:
    """Degrade to the deterministic baseline when the semantic model fails.

    The annotation failure stays a review/ops signal on the manifest instead
    of a dead-lettered document with zero extraction coverage.
    """
    telemetry = {
        "version": DETERMINISTIC_PLANNER_VERSION,
        "fingerprint": baseline_plan_fingerprint(source, baseline),
        "baseline_region_count": len(baseline.regions),
        "qwen_annotation_failed": True,
        "failure_reason": failure_reason[:500],
    }
    manifest_payload = dict(baseline.manifest)
    manifest_payload["deterministic_baseline"] = telemetry
    confidence = dict(baseline.confidence)
    confidence["deterministic_baseline"] = telemetry
    manifest = replace(
        baseline,
        confidence=confidence,
        manifest=manifest_payload,
        review_required=True,
        escalation_reason=f"qwen_annotation_failed:{failure_reason[:200]}",
    )
    return SemanticAnnotationResult(manifest=manifest, status="succeeded")


def _baseline_region_covered(
    baseline_region: SemanticRegionAnnotation,
    plan_regions: list[SemanticRegionAnnotation],
) -> bool:
    table_id = baseline_region.grounding.table_id
    if table_id is not None:
        return any(
            region.grounding.table_id == table_id
            and region.granite_task is not None
            and region.granite_task != "ignore"
            for region in plan_regions
        )
    return any(
        region.semantic_type == baseline_region.semantic_type
        and region.granite_task is not None
        and region.granite_task != "ignore"
        for region in plan_regions
    )


def _region_identity(
    region: SemanticRegionAnnotation,
    page_numbers: dict[str, int],
) -> str:
    grounding = region.grounding
    page_number = None
    if grounding.page_id is not None:
        page_number = page_numbers.get(str(grounding.page_id))
    identity: dict[str, Any] = {
        "semantic_type": region.semantic_type,
        "granite_task": region.granite_task,
        "target_schema": region.target_schema,
        "grounding_kind": grounding.kind,
        "page_number": region.metadata.get("docling_table_page_number") or page_number,
        "table_index": region.metadata.get("docling_table_index"),
        "expected_fields": list(region.expected_fields),
    }
    return json.dumps(identity, sort_keys=True, separators=(",", ":"))
