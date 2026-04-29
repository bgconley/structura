from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from lib.extraction.models import ExtractionSourceDocument
from lib.semantic_annotations.docling_audit import build_docling_audit
from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    PageSemanticAnnotation,
    SemanticRegionAnnotation,
)

FALLBACK_DOCUMENT_TYPE = "generic_form"

_DOCUMENT_TYPE_ALIASES = {
    "document_observation": FALLBACK_DOCUMENT_TYPE,
}

_EVIDENCE_FAMILY_BY_DOCUMENT_TYPE = {
    "medical_eob": "medical_eob",
    "insurance_denial": "medical_eob",
    "medical_bill": "medical_eob",
    "invoice": "invoice",
    "receipt": "receipt",
    "payment_receipt": "receipt",
    "travel_receipt": "receipt",
    "restaurant_receipt": "receipt",
    "service_record": "receipt",
    "retail_order": "retail_order",
    "real_estate_title": "real_estate_title",
    "mortgage_escrow_statement": "mortgage_escrow_statement",
    "financial_dispute_form": "financial_dispute_form",
}
_UNSPECIFIC_DOCUMENT_TYPES = {
    "generic_form",
    "unsupported_document",
    "no_extraction_target",
    "legal",
    "tax",
    "financial",
    "other",
    "unknown",
}
_ANCHOR_VOTE_WEIGHT = 1.25
_SOURCE_FAMILY_VOTE_WEIGHT = 0.35
_PARTIAL_DOCUMENT_TYPE_WEIGHT = 0.5
_UNANCHORED_CONFLICT_MARGIN = 0.5
_PAGE_MANIFEST_METADATA_FIELDS = (
    "page_family_hints",
    "continuation_group",
    "docling_table_signal",
    "requires_cross_page_context",
    "material_region_count_hint",
)
_REGION_MANIFEST_METADATA_FIELDS = (
    "importance",
    "source_signal",
    "coverage_role",
    "extraction_scope",
    "requires_full_page_image",
    "continuation_group",
    "must_extract_reason",
    "negative_routing_reason",
    "min_expected_items",
    "visual_bbox_hint",
)


@dataclass(frozen=True)
class DocumentTypeResolution:
    selected: str
    votes: dict[str, float]
    page_votes: dict[str, float]
    partial_votes: dict[str, float]
    anchor_hints: tuple[str, ...]
    source_family: str | None
    reason: str

    def to_json(self) -> dict[str, Any]:
        return {
            "selected": self.selected,
            "votes": self.votes,
            "page_votes": self.page_votes,
            "partial_votes": self.partial_votes,
            "docling_anchor_hints": list(self.anchor_hints),
            "source_family": self.source_family,
            "reason": self.reason,
        }


def merge_partial_manifests(
    source: ExtractionSourceDocument,
    partials: list[DocumentSemanticManifest],
    *,
    quality_mode: str,
    profile_name: str,
    prompt_version: str,
) -> DocumentSemanticManifest:
    pages = [page for partial in partials for page in partial.pages]
    regions = [region for partial in partials for region in partial.regions]
    confidence_parts = [partial.confidence for partial in partials if partial.confidence]
    overall_values = [
        float(confidence["overall"])
        for confidence in confidence_parts
        if isinstance(confidence.get("overall"), int | float)
    ]
    document_type_resolution = resolve_document_type(source, partials)
    confidence: dict[str, object] = {
        "chunk_count": len(partials),
        "chunks": confidence_parts,
        "document_type_resolution": document_type_resolution.to_json(),
    }
    if overall_values:
        confidence["overall"] = sum(overall_values) / len(overall_values)
    manifest_payload: dict[str, object] = {
        "schema_name": "semantic_annotation_manifest",
        "schema_version": "v1",
        "document_type": document_type_resolution.selected,
        "pages": [page_manifest_json(page) for page in pages],
        "regions": [region_manifest_json(region) for region in regions],
        "quality_flags": {
            "needs_high_quality_pass": any(
                bool(partial.manifest.get("quality_flags", {}).get("needs_high_quality_pass"))
                for partial in partials
                if isinstance(partial.manifest.get("quality_flags"), dict)
            ),
            "visual_degradation": any(
                bool(partial.manifest.get("quality_flags", {}).get("visual_degradation"))
                for partial in partials
                if isinstance(partial.manifest.get("quality_flags"), dict)
            ),
        },
        "confidence": confidence,
    }
    document_type_candidates = _document_type_candidates_from_partials(
        document_type_resolution,
        partials,
    )
    if document_type_candidates:
        manifest_payload["document_type_candidates"] = document_type_candidates
    planner_notes = _planner_notes_from_partials(partials)
    if planner_notes:
        manifest_payload["planner_notes"] = planner_notes
    return DocumentSemanticManifest(
        document_id=source.document_id,
        household_id=source.household_id,
        quality_mode=quality_mode,  # type: ignore[arg-type]
        profile_name=profile_name,
        source_engine=partials[0].source_engine,
        model_name=partials[0].model_name,
        model_version=partials[0].model_version,
        prompt_version=prompt_version,
        pages=pages,
        regions=regions,
        confidence=confidence,
        manifest=manifest_payload,
        review_required=any(region.review_required for region in regions),
        input_page_hashes=tuple(
            page_hash for partial in partials for page_hash in partial.input_page_hashes
        ),
    )


def resolve_document_type(
    source: ExtractionSourceDocument,
    partials: list[DocumentSemanticManifest],
) -> DocumentTypeResolution:
    page_votes: defaultdict[str, float] = defaultdict(float)
    partial_votes: defaultdict[str, float] = defaultdict(float)
    votes: defaultdict[str, float] = defaultdict(float)
    for partial in partials:
        document_type = _normalized_document_type(partial.manifest.get("document_type"))
        if document_type:
            partial_votes[document_type] += _PARTIAL_DOCUMENT_TYPE_WEIGHT
            votes[document_type] += _PARTIAL_DOCUMENT_TYPE_WEIGHT
        for page in partial.pages:
            hint = _normalized_document_type(page.document_type_hint)
            if hint:
                weight = _confidence_weight(page.confidence)
                page_votes[hint] += weight
                votes[hint] += weight

    audit = build_docling_audit(source)
    anchor_hints = tuple(audit.suggested_family_hints)
    for hint in anchor_hints:
        votes[hint] += _ANCHOR_VOTE_WEIGHT
    source_family = _normalized_document_type(source.family)
    if source_family and source_family not in _UNSPECIFIC_DOCUMENT_TYPES:
        votes[source_family] += _SOURCE_FAMILY_VOTE_WEIGHT

    if not votes:
        return DocumentTypeResolution(
            selected=source_family or FALLBACK_DOCUMENT_TYPE,
            votes={},
            page_votes={},
            partial_votes={},
            anchor_hints=anchor_hints,
            source_family=source_family,
            reason="no_model_votes",
        )

    ranked = sorted(votes.items(), key=lambda item: (-item[1], item[0]))
    selected = ranked[0][0]
    reason = "top_weighted_vote"
    if _should_downgrade_to_generic_form(
        selected=selected,
        ranked=ranked,
        anchor_hints=anchor_hints,
    ):
        selected = FALLBACK_DOCUMENT_TYPE
        reason = "conflicting_unanchored_page_votes"
    return DocumentTypeResolution(
        selected=selected,
        votes=_sorted_votes(votes),
        page_votes=_sorted_votes(page_votes),
        partial_votes=_sorted_votes(partial_votes),
        anchor_hints=anchor_hints,
        source_family=source_family,
        reason=reason,
    )


def page_manifest_json(page: PageSemanticAnnotation) -> dict[str, object]:
    payload: dict[str, object] = {
        "page_id": str(page.page_id),
        "page_number": page.page_number,
        "page_role": page.page_role,
        "document_type_hint": page.document_type_hint,
        "extraction_usefulness": page.extraction_usefulness,
        "is_boilerplate": page.is_boilerplate,
        "has_structured_targets": page.has_structured_targets,
        "ambiguous": page.ambiguous,
        "escalation_required": page.escalation_required,
        "escalation_reasons": list(page.metadata.get("escalation_reasons", []))
        if isinstance(page.metadata.get("escalation_reasons"), list)
        else [],
        "reason": page.reason,
        "confidence": page.confidence,
    }
    payload.update(_manifest_metadata(page.metadata, _PAGE_MANIFEST_METADATA_FIELDS))
    return payload


def region_manifest_json(region: SemanticRegionAnnotation) -> dict[str, object]:
    payload: dict[str, object] = {
        "semantic_type": region.semantic_type,
        "priority": region.priority,
        "granite_task": region.granite_task,
        "target_schema": region.target_schema,
        "expected_fields": list(region.expected_fields),
        "grounding": {
            "kind": region.grounding.kind,
            "page_id": str(region.grounding.page_id) if region.grounding.page_id else None,
            "element_id": (
                str(region.grounding.element_id) if region.grounding.element_id else None
            ),
            "table_id": str(region.grounding.table_id) if region.grounding.table_id else None,
        },
        "review_required": region.review_required,
        "reason": region.reason,
        "confidence": region.confidence,
    }
    payload.update(_manifest_metadata(region.metadata, _REGION_MANIFEST_METADATA_FIELDS))
    return payload


def _manifest_metadata(
    metadata: dict[str, Any],
    allowed_fields: tuple[str, ...],
) -> dict[str, object]:
    return {field: metadata[field] for field in allowed_fields if field in metadata}


def _document_type_candidates_from_partials(
    resolution: DocumentTypeResolution,
    partials: list[DocumentSemanticManifest],
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    seen: set[str] = set()
    for partial in partials:
        raw_candidates = partial.manifest.get("document_type_candidates")
        if not isinstance(raw_candidates, list):
            continue
        for item in raw_candidates:
            if not isinstance(item, dict):
                continue
            document_type = _normalized_document_type(item.get("document_type"))
            if document_type is None or document_type in seen:
                continue
            candidates.append(
                {
                    "document_type": document_type,
                    "confidence": item.get("confidence"),
                    "evidence_terms": _string_list(item.get("evidence_terms"), limit=8),
                    "reason": item.get("reason") if isinstance(item.get("reason"), str) else None,
                }
            )
            seen.add(document_type)
            if len(candidates) >= 4:
                return candidates
    max_score = max(resolution.votes.values(), default=1.0)
    for document_type, score in resolution.votes.items():
        if document_type in seen:
            continue
        candidates.append(
            {
                "document_type": document_type,
                "confidence": min(1.0, max(0.0, score / max(1.0, max_score))),
                "evidence_terms": list(resolution.anchor_hints)[:8],
                "reason": resolution.reason,
            }
        )
        seen.add(document_type)
        if len(candidates) >= 4:
            break
    return candidates


def _planner_notes_from_partials(partials: list[DocumentSemanticManifest]) -> list[str]:
    notes: list[str] = []
    for partial in partials:
        raw_notes = partial.manifest.get("planner_notes")
        if not isinstance(raw_notes, list):
            continue
        for item in raw_notes:
            if not isinstance(item, str):
                continue
            note = item.strip()
            if note and note not in notes:
                notes.append(note[:160])
                if len(notes) >= 6:
                    return notes
    return notes


def _string_list(value: object, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip()[:64] for item in value if isinstance(item, str) and item.strip()][:limit]


def _should_downgrade_to_generic_form(
    *,
    selected: str,
    ranked: list[tuple[str, float]],
    anchor_hints: tuple[str, ...],
) -> bool:
    meaningful_families = {
        family
        for document_type, _score in ranked
        if (family := _EVIDENCE_FAMILY_BY_DOCUMENT_TYPE.get(document_type)) is not None
    }
    if len(meaningful_families) < 2:
        return False
    selected_family = _EVIDENCE_FAMILY_BY_DOCUMENT_TYPE.get(selected)
    if selected_family in anchor_hints:
        return False
    if len(ranked) < 2:
        return False
    return ranked[0][1] - ranked[1][1] < _UNANCHORED_CONFLICT_MARGIN


def _normalized_document_type(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    return _DOCUMENT_TYPE_ALIASES.get(normalized, normalized)


def _confidence_weight(value: float | None) -> float:
    if value is None:
        return 0.5
    return max(0.1, min(float(value), 1.0))


def _sorted_votes(votes: defaultdict[str, float]) -> dict[str, float]:
    return {
        document_type: round(score, 4)
        for document_type, score in sorted(votes.items(), key=lambda item: (-item[1], item[0]))
    }
