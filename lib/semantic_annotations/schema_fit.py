from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lib.extraction.models import ExtractionSourceDocument
from lib.semantic_annotations.docling_audit import family_anchor_hits
from lib.semantic_annotations.models import SemanticRegionAnnotation
from lib.semantic_annotations.target_schema_policy import preferred_target_schema

_TARGET_SCHEMA_EVIDENCE_FAMILIES = {
    "invoice": frozenset({"invoice"}),
    "receipt": frozenset({"receipt", "retail_order"}),
    "medical_eob": frozenset({"medical_eob"}),
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
    requested = preferred_target_schema(
        document_family=source.family,
        document_metadata=source.metadata,
        document_type_hint=document_type_hint,
        semantic_type=region.semantic_type,
        model_target_schema=region.target_schema,
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

    evidence_families = _evidence_families(source)
    allowed_evidence_families = _TARGET_SCHEMA_EVIDENCE_FAMILIES[requested]
    document_type = _normalized(document_type_hint)
    if (
        document_type in _OBSERVATION_DOCUMENT_TYPES
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
    if allowed_evidence_families.intersection(evidence_families):
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
    return tuple(
        sorted(family for family, anchors in family_anchor_hits(source).items() if anchors)
    )


def _normalized(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None
