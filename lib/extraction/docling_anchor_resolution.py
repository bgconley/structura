from __future__ import annotations

from lib.extraction.evidence import normalize_bbox
from lib.extraction.models import ExtractionSourceDocument, ParsedElementText
from lib.extraction.region_envelope import (
    EvidenceRef,
    RegionExtractionEnvelope,
    RegionFact,
    RegionLineItem,
)

_MIN_ANCHOR_TEXT_LENGTH = 3


def resolve_docling_anchors_for_envelope(
    envelope: RegionExtractionEnvelope,
    source: ExtractionSourceDocument,
) -> tuple[RegionExtractionEnvelope, int]:
    """Upgrade page-only model evidence with deterministic Docling anchors.

    Granite values extracted from full-page visual inputs carry only page
    lineage; per ADR 0005 they cannot become Claims without a structural
    anchor, which silently drops every KVP value on the document. Docling is
    the anchor coordinate system, so the verbatim source text is located in
    the parsed elements (element_id + bbox) or page text (text_span). Refs
    with no deterministic match stay page-only and remain excluded from
    Claims.
    """
    copied = envelope.model_copy(deep=True)
    resolved_count = 0
    for fact in copied.facts:
        resolved_count += _upgrade_owner_evidence(fact, source)
    for line_item in copied.line_items:
        resolved_count += _upgrade_owner_evidence(line_item, source)
    for observation in copied.observations:
        resolved_count += _upgrade_owner_evidence(observation, source)
    return copied, resolved_count


def _upgrade_owner_evidence(
    owner: RegionFact | RegionLineItem,
    source: ExtractionSourceDocument,
) -> int:
    resolved_count = 0
    refs = list(owner.evidence)
    upgraded: list[EvidenceRef] = []
    for ref in refs:
        if _has_structural_locator(ref):
            upgraded.append(ref)
            continue
        resolved = _resolve_ref(ref, source)
        if resolved is not None:
            resolved_count += 1
            upgraded.append(resolved)
        else:
            upgraded.append(ref)
    owner.evidence = upgraded
    return resolved_count


def _has_structural_locator(ref: EvidenceRef) -> bool:
    return (
        bool(ref.element_id)
        or ref.bbox is not None
        or ref.text_span is not None
        or (bool(ref.table_id) and ref.row_index is not None)
    )


def _resolve_ref(ref: EvidenceRef, source: ExtractionSourceDocument) -> EvidenceRef | None:
    text = (ref.source_text or "").strip()
    if len(text) < _MIN_ANCHOR_TEXT_LENGTH or ref.page_number is None:
        return None
    lowered = text.lower()

    element = _matching_element(source, page_number=ref.page_number, lowered_text=lowered)
    if element is not None:
        update: dict[str, object] = {"element_id": str(element.element_id)}
        bbox = normalize_bbox(element.bbox)
        if bbox:
            update["bbox"] = bbox
        return ref.model_copy(update=update)

    for page in source.pages:
        if page.page_number != ref.page_number:
            continue
        start = page.text.lower().find(lowered)
        if start >= 0:
            return ref.model_copy(
                update={
                    "text_span": {
                        "start": start,
                        "end": start + len(text),
                        "basis": "page_text",
                    }
                }
            )
    return None


def _matching_element(
    source: ExtractionSourceDocument,
    *,
    page_number: int,
    lowered_text: str,
) -> ParsedElementText | None:
    for element in source.elements:
        if element.page_number != page_number:
            continue
        if element.text and lowered_text in element.text.lower():
            return element
    return None
