from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lib.extraction.models import ExtractionSourceDocument
from lib.semantic_annotations.docling_audit import (
    family_anchor_hits,
    family_has_required_hint_fit,
)
from lib.semantic_annotations.docling_targets import DOCLING_STRUCTURAL_REGION_SOURCE
from lib.semantic_annotations.models import SemanticRegionAnnotation
from lib.semantic_annotations.target_schema_policy import (
    classified_document_target_schema,
    preferred_target_schema,
    target_schema_from_document_hint,
    target_schema_from_semantic_type,
)

_TARGET_SCHEMA_EVIDENCE_FAMILIES = {
    "invoice": frozenset({"invoice"}),
    "receipt": frozenset({"receipt", "retail_order", "service_record"}),
    "medical_eob": frozenset({"medical_eob"}),
}
_TARGET_SCHEMA_REQUIRED_ANCHOR_COUNTS = {
    "invoice": 1,
    "receipt": 2,
    "medical_eob": 2,
}
_OBSERVATION_CONFLICT_FAMILIES = frozenset(
    {"real_estate_title", "mortgage_escrow_statement", "financial_dispute_form"}
)
_OBSERVATION_CONFLICT_REQUIRED_ANCHOR_COUNTS = {
    "real_estate_title": 2,
    "mortgage_escrow_statement": 1,
    "financial_dispute_form": 2,
}
_OBSERVATION_DOCUMENT_TYPES = {
    "document_observation",
    "real_estate_title",
    "mortgage_escrow_statement",
    "financial_dispute_form",
    "generic_form",
    "unsupported_document",
    "no_extraction_target",
}
_OBSERVATION_SEMANTIC_TYPES = {
    "seller_information_block",
    "escrow_summary",
    "mortgage_payment_summary",
    "dispute_transaction_table",
    "dispute_reason_block",
    "generic_form_kvp",
    "unsupported_document_region",
}


@dataclass(frozen=True)
class SchemaFitDecision:
    target_schema: str | None
    requested_target_schema: str | None
    evidence_families: tuple[str, ...]
    document_type_hint: str | None
    reason: str
    downgraded: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "target_schema": self.target_schema,
            "requested_target_schema": self.requested_target_schema,
            "evidence_families": list(self.evidence_families),
            "document_type_hint": self.document_type_hint,
            "reason": self.reason,
            "downgraded": self.downgraded,
        }


def schema_fit_for_region(
    *,
    source: ExtractionSourceDocument,
    region: SemanticRegionAnnotation,
    document_type_hint: str | None,
) -> SchemaFitDecision:
    requested = _requested_target_schema(
        source=source,
        region=region,
        document_type_hint=document_type_hint,
    )
    if requested is None:
        return SchemaFitDecision(
            target_schema=None,
            requested_target_schema=None,
            evidence_families=(),
            document_type_hint=_normalized(document_type_hint),
            reason="no_supported_target_schema",
        )
    if requested == "document_observation":
        return SchemaFitDecision(
            target_schema=requested,
            requested_target_schema=requested,
            evidence_families=_evidence_families(source),
            document_type_hint=_normalized(document_type_hint),
            reason="observation_schema",
        )

    anchor_hits = family_anchor_hits(source)
    evidence_families = _evidence_families_from_hits(anchor_hits)
    allowed_evidence_families = _TARGET_SCHEMA_EVIDENCE_FAMILIES[requested]
    document_type = _normalized(document_type_hint)
    is_docling_structural = region.metadata.get("region_source") == DOCLING_STRUCTURAL_REGION_SOURCE
    if (
        (document_type in _OBSERVATION_DOCUMENT_TYPES and not is_docling_structural)
        or region.semantic_type in _OBSERVATION_SEMANTIC_TYPES
    ):
        return SchemaFitDecision(
            target_schema="document_observation",
            requested_target_schema=requested,
            evidence_families=evidence_families,
            document_type_hint=document_type,
            reason="observation_document_or_region_type",
            downgraded=True,
        )
    if _conflicting_observation_families(anchor_hits) and not _has_required_anchor_fit(
        requested, anchor_hits
    ):
        return SchemaFitDecision(
            target_schema="document_observation",
            requested_target_schema=requested,
            evidence_families=evidence_families,
            document_type_hint=document_type,
            reason="conflicting_docling_observation_anchors",
            downgraded=True,
        )
    if allowed_evidence_families.intersection(evidence_families) and _has_required_anchor_fit(
        requested, anchor_hits
    ):
        return SchemaFitDecision(
            target_schema=requested,
            requested_target_schema=requested,
            evidence_families=evidence_families,
            document_type_hint=document_type,
            reason="docling_anchor_fit",
        )
    return SchemaFitDecision(
        target_schema="document_observation",
        requested_target_schema=requested,
        evidence_families=evidence_families,
        document_type_hint=document_type,
        reason="missing_required_docling_anchors",
        downgraded=True,
    )


def _evidence_families(source: ExtractionSourceDocument) -> tuple[str, ...]:
    return _evidence_families_from_hits(family_anchor_hits(source))


def _requested_target_schema(
    *,
    source: ExtractionSourceDocument,
    region: SemanticRegionAnnotation,
    document_type_hint: str | None,
) -> str | None:
    if region.metadata.get("region_source") == DOCLING_STRUCTURAL_REGION_SOURCE:
        return (
            target_schema_from_semantic_type(region.semantic_type)
            or target_schema_from_document_hint(region.target_schema)
            or target_schema_from_document_hint(document_type_hint)
            or classified_document_target_schema(source.family, source.metadata)
            or target_schema_from_document_hint(source.family)
        )
    return preferred_target_schema(
        document_family=source.family,
        document_metadata=source.metadata,
        document_type_hint=document_type_hint,
        semantic_type=region.semantic_type,
        model_target_schema=region.target_schema,
    )


def _evidence_families_from_hits(anchor_hits: dict[str, tuple[str, ...]]) -> tuple[str, ...]:
    return tuple(
        sorted(
            family
            for family, anchors in anchor_hits.items()
            if anchors and family_has_required_hint_fit(family, anchors)
        )
    )


def _has_required_anchor_fit(
    requested: str,
    anchor_hits: dict[str, tuple[str, ...]],
) -> bool:
    allowed = _TARGET_SCHEMA_EVIDENCE_FAMILIES[requested]
    required_count = _TARGET_SCHEMA_REQUIRED_ANCHOR_COUNTS[requested]
    return any(
        len(anchor_hits.get(family, ())) >= required_count
        and family_has_required_hint_fit(family, anchor_hits.get(family, ()))
        for family in allowed
    )


def _conflicting_observation_families(
    anchor_hits: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    conflicts = [
        family
        for family in _OBSERVATION_CONFLICT_FAMILIES
        if len(anchor_hits.get(family, ()))
        >= _OBSERVATION_CONFLICT_REQUIRED_ANCHOR_COUNTS[family]
        and family_has_required_hint_fit(family, anchor_hits.get(family, ()))
    ]
    return tuple(sorted(conflicts))


def _normalized(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None
