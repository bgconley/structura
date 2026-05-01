from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from psycopg.types.json import Jsonb

from lib.extraction.models import ExtractionSourceDocument
from lib.semantic_annotations.docling_audit import build_docling_audit
from lib.semantic_annotations.models import DocumentSemanticManifest

PERSISTABLE_DOCUMENT_FAMILIES = frozenset(
    {
        "generic",
        "receipt",
        "invoice",
        "medical_eob",
        "medical_bill",
        "insurance_document",
        "insurance_denial",
        "legal_contract",
        "legal_notice",
        "tax_document",
        "warranty",
        "identity_document",
        "bank_statement",
        "financial_statement",
        "handwritten_note",
        "typed_note",
        "whitepaper",
        "reference_document",
        "retail_order",
        "service_record",
        "real_estate_title",
        "mortgage_escrow_statement",
        "financial_dispute_form",
    }
)


_DOCUMENT_TYPE_FAMILY_MAP = {
    "invoice": "invoice",
    "receipt": "receipt",
    "payment_receipt": "receipt",
    "travel_receipt": "receipt",
    "restaurant_receipt": "receipt",
    "medical_eob": "medical_eob",
    "medical_bill": "medical_bill",
    "medical_claim": "medical_eob",
    "insurance_denial": "insurance_denial",
    "insurance_document": "insurance_document",
    "retail_order": "retail_order",
    "service_record": "service_record",
    "real_estate_title": "real_estate_title",
    "mortgage_escrow_statement": "mortgage_escrow_statement",
    "financial_dispute_form": "financial_dispute_form",
    "generic_form": "generic",
    "unsupported_document": "generic",
    "no_extraction_target": "generic",
}
_SUPPORTING_ANCHOR_FAMILY = {
    "insurance_denial": "medical_eob",
    "insurance_document": "medical_eob",
    "medical_bill": "medical_eob",
    "medical_eob": "medical_eob",
    "receipt": "receipt",
    "invoice": "invoice",
    "retail_order": "retail_order",
    "service_record": "service_record",
    "real_estate_title": "real_estate_title",
    "mortgage_escrow_statement": "mortgage_escrow_statement",
    "financial_dispute_form": "financial_dispute_form",
}
_DOCLING_SUPERSEDING_FAMILIES = (
    "real_estate_title",
    "mortgage_escrow_statement",
    "financial_dispute_form",
    "service_record",
    "retail_order",
)
_SPECIFIC_PHASE4_FAMILIES = frozenset(
    {
        "receipt",
        "invoice",
        "medical_eob",
        "medical_bill",
        "insurance_document",
        "generic",
    }
)
_OVERCLASSIFIABLE_PHASE4_FAMILIES = frozenset(
    {
        "receipt",
        "invoice",
        "medical_eob",
        "medical_bill",
        "insurance_document",
    }
)
_GENERIC_SEMANTIC_DOCUMENT_TYPES = frozenset(
    {
        "document_observation",
        "generic_form",
        "unsupported_document",
        "no_extraction_target",
    }
)


@dataclass(frozen=True)
class SemanticDocumentFamilyDecision:
    family: str
    subtype: str | None
    confidence: float
    should_update: bool
    reason: str
    semantic_document_type: str | None
    docling_family_hints: tuple[str, ...]
    source_family: str

    def to_json(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "subtype": self.subtype,
            "confidence": self.confidence,
            "should_update": self.should_update,
            "reason": self.reason,
            "semantic_document_type": self.semantic_document_type,
            "docling_family_hints": list(self.docling_family_hints),
            "source_family": self.source_family,
            "version": "phase8_5_semantic_family_reconciliation_v1",
        }


def semantic_document_family_decision(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
) -> SemanticDocumentFamilyDecision:
    audit = build_docling_audit(source)
    docling_hints = tuple(audit.suggested_family_hints)
    semantic_document_type = _normalized(manifest.manifest.get("document_type"))
    semantic_family = _DOCUMENT_TYPE_FAMILY_MAP.get(semantic_document_type or "")
    if semantic_family and _has_docling_support(semantic_family, docling_hints):
        return _decision(
            source=source,
            family=semantic_family,
            confidence=_confidence(audit.anchor_counts.get(_support_family(semantic_family), 0)),
            reason="semantic_document_type_with_docling_support"
            if semantic_family != _normalized(source.family)
            else "semantic_document_type_confirms_existing_family",
            semantic_document_type=semantic_document_type,
            docling_hints=docling_hints,
        )

    docling_family = _dominant_docling_family(docling_hints)
    if (
        docling_family
        and docling_family != _normalized(source.family)
        and _can_docling_family_supersede_source(source.family, docling_family)
    ):
        return _decision(
            source=source,
            family=docling_family,
            confidence=_confidence(audit.anchor_counts.get(docling_family, 0)),
            reason="docling_anchor_family_supersedes_phase4",
            semantic_document_type=semantic_document_type,
            docling_hints=docling_hints,
        )

    source_family = _normalized(source.family) or "generic"
    if (
        source_family in _OVERCLASSIFIABLE_PHASE4_FAMILIES
        and semantic_document_type in _GENERIC_SEMANTIC_DOCUMENT_TYPES
        and not _has_docling_support(source_family, docling_hints)
    ):
        return _decision(
            source=source,
            family="generic",
            confidence=0.68,
            reason="semantic_generic_downgrades_unsupported_phase4_family",
            semantic_document_type=semantic_document_type,
            docling_hints=docling_hints,
        )

    return _decision(
        source=source,
        family=source_family,
        confidence=0.62,
        reason="retain_existing_family",
        semantic_document_type=semantic_document_type,
        docling_hints=docling_hints,
        should_update=False,
    )


def source_with_semantic_family(
    source: ExtractionSourceDocument,
    decision: SemanticDocumentFamilyDecision,
) -> ExtractionSourceDocument:
    if not decision.should_update:
        return source
    metadata = {
        **source.metadata,
        "phase8_5": {
            **_mapping(source.metadata.get("phase8_5")),
            "semantic_classification": decision.to_json(),
        },
    }
    return replace(
        source,
        family=decision.family,
        subtype=decision.subtype,
        metadata=metadata,
    )


def apply_semantic_document_family_decision_with_cursor(
    cur: Any,
    source: ExtractionSourceDocument,
    decision: SemanticDocumentFamilyDecision,
) -> None:
    metadata_patch = Jsonb({"semantic_classification": decision.to_json()})
    if decision.should_update and decision.family in PERSISTABLE_DOCUMENT_FAMILIES:
        cur.execute(
            """
            UPDATE documents
            SET document_family = %s::document_family_enum,
                document_subtype = %s,
                family_confidence = %s,
                sensitivity = CASE
                  WHEN %s = 'medical_eob' THEN 'medical'::sensitivity_enum
                  ELSE sensitivity
                END,
                metadata_json = jsonb_set(
                  COALESCE(metadata_json, '{}'::jsonb),
                  '{phase8_5}',
                  COALESCE(metadata_json->'phase8_5', '{}'::jsonb) || %s::jsonb,
                  true
                ),
                updated_at = now()
            WHERE id = %s
            """,
            (
                decision.family,
                decision.subtype,
                decision.confidence,
                decision.family,
                metadata_patch,
                source.document_id,
            ),
        )
        return
    cur.execute(
        """
        UPDATE documents
        SET metadata_json = jsonb_set(
              COALESCE(metadata_json, '{}'::jsonb),
              '{phase8_5}',
              COALESCE(metadata_json->'phase8_5', '{}'::jsonb) || %s::jsonb,
              true
            ),
            updated_at = now()
        WHERE id = %s
        """,
        (metadata_patch, source.document_id),
    )


def _decision(
    *,
    source: ExtractionSourceDocument,
    family: str,
    confidence: float,
    reason: str,
    semantic_document_type: str | None,
    docling_hints: tuple[str, ...],
    should_update: bool | None = None,
) -> SemanticDocumentFamilyDecision:
    normalized_family = family if family in PERSISTABLE_DOCUMENT_FAMILIES else "generic"
    normalized_source_family = _normalized(source.family) or "generic"
    update = (
        normalized_family != normalized_source_family if should_update is None else should_update
    )
    return SemanticDocumentFamilyDecision(
        family=normalized_family,
        subtype=source.subtype,
        confidence=round(confidence, 4),
        should_update=update,
        reason=reason,
        semantic_document_type=semantic_document_type,
        docling_family_hints=docling_hints,
        source_family=normalized_source_family,
    )


def _has_docling_support(family: str, docling_hints: tuple[str, ...]) -> bool:
    support_family = _support_family(family)
    return support_family in docling_hints


def _support_family(family: str) -> str:
    return _SUPPORTING_ANCHOR_FAMILY.get(family, family)


def _dominant_docling_family(docling_hints: tuple[str, ...]) -> str | None:
    for family in _DOCLING_SUPERSEDING_FAMILIES:
        if family in docling_hints:
            return family
    return None


def _can_docling_family_supersede_source(source_family: str, docling_family: str) -> bool:
    normalized_source = _normalized(source_family) or "generic"
    if docling_family in {
        "real_estate_title",
        "mortgage_escrow_statement",
        "financial_dispute_form",
    }:
        return True
    return normalized_source in _SPECIFIC_PHASE4_FAMILIES


def _confidence(anchor_count: int | None) -> float:
    return min(0.96, 0.72 + ((anchor_count or 0) * 0.04))


def _normalized(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}
