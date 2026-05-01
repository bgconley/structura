from __future__ import annotations

from copy import deepcopy
from typing import Any

from lib.extraction.evidence_context import EvidenceContext

_SKIP_RECURSION_KEYS = {
    "confidence",
    "crop_quality",
    "evidence",
    "metadata",
    "normalization_json",
    "validation",
    "visual_input_attempt",
}

_EVIDENCE_CONTAINER_KEYS = {
    "amount",
    "allowed_amount",
    "billed_amount",
    "claim_number",
    "date_local",
    "description",
    "display_name",
    "field_name",
    "financial_summary",
    "gross_amount",
    "line_items",
    "merchant",
    "net_amount",
    "observations",
    "paid_amount",
    "patient_responsibility",
    "provider",
    "service_description",
    "service_lines",
    "subtotal",
    "tax",
    "tip",
    "total",
    "transaction",
    "unit_price",
    "value",
}


def concretize_normalized_evidence(
    payload: dict[str, Any],
    evidence_context: EvidenceContext | None,
) -> dict[str, Any]:
    if evidence_context is None:
        return payload

    copied = deepcopy(payload)
    _concretize_node(copied, evidence_context, is_root=True)
    return copied


def evidence_ref_from_context(
    *,
    evidence_context: EvidenceContext,
    source_text: object | None = None,
    confidence: float | None = None,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "document_id": str(evidence_context.document_id),
        "source_engine": evidence_context.source_engine,
    }
    if source_text not in (None, ""):
        evidence["source_text"] = str(source_text)
    if confidence is not None:
        evidence["confidence"] = confidence
    else:
        evidence["confidence"] = 0.72
    if evidence_context.semantic_annotation_id is not None:
        evidence["semantic_annotation_id"] = str(evidence_context.semantic_annotation_id)
    if evidence_context.semantic_region_id is not None:
        evidence["semantic_region_id"] = str(evidence_context.semantic_region_id)
    if evidence_context.page_id is not None:
        evidence["page_id"] = str(evidence_context.page_id)
    if evidence_context.page_number is not None:
        evidence["page_number"] = evidence_context.page_number
    if evidence_context.element_id is not None:
        evidence["element_id"] = str(evidence_context.element_id)
    if evidence_context.table_id is not None:
        evidence["table_id"] = str(evidence_context.table_id)
    if evidence_context.visual_input_scope is not None:
        evidence["visual_input_scope"] = evidence_context.visual_input_scope
    if evidence_context.visual_input_sha256 is not None:
        evidence["visual_input_sha256"] = evidence_context.visual_input_sha256
    if evidence_context.source_page_image_sha256 is not None:
        evidence["source_page_image_sha256"] = evidence_context.source_page_image_sha256
    if evidence_context.bbox is not None:
        evidence["bbox"] = evidence_context.bbox
    if evidence_context.bbox_basis is not None:
        evidence["bbox_basis"] = evidence_context.bbox_basis
    if evidence_context.original_bbox is not None:
        evidence["original_bbox"] = evidence_context.original_bbox
    if evidence_context.expanded_bbox is not None:
        evidence["expanded_bbox"] = evidence_context.expanded_bbox
    if evidence_context.rotation_policy is not None:
        evidence["rotation_policy"] = evidence_context.rotation_policy
    if evidence_context.crop_quality is not None:
        evidence["crop_quality"] = evidence_context.crop_quality
    if evidence_context.visual_input_attempt is not None:
        evidence["visual_input_attempt"] = evidence_context.visual_input_attempt
    return {key: value for key, value in evidence.items() if value not in (None, "")}


def _concretize_node(
    value: Any,
    evidence_context: EvidenceContext,
    *,
    is_root: bool = False,
) -> None:
    if isinstance(value, dict):
        if is_root or _should_attach_evidence(value):
            _ensure_evidence(value, evidence_context)
        for key, child in list(value.items()):
            if key in _SKIP_RECURSION_KEYS:
                continue
            _concretize_node(child, evidence_context)
    elif isinstance(value, list):
        for child in value:
            _concretize_node(child, evidence_context)


def _should_attach_evidence(value: dict[str, Any]) -> bool:
    return bool(_EVIDENCE_CONTAINER_KEYS.intersection(value.keys()))


def _ensure_evidence(value: dict[str, Any], evidence_context: EvidenceContext) -> None:
    evidence = value.get("evidence")
    if isinstance(evidence, list) and evidence:
        value["evidence"] = [
            _merge_ref(entry, evidence_context)
            for entry in evidence
            if isinstance(entry, dict)
        ]
        return
    value["evidence"] = [
        evidence_ref_from_context(
            evidence_context=evidence_context,
            source_text=_source_text(value),
            confidence=_confidence(value),
        )
    ]


def _merge_ref(
    evidence: dict[str, Any],
    evidence_context: EvidenceContext,
) -> dict[str, Any]:
    contextual = evidence_ref_from_context(
        evidence_context=evidence_context,
        source_text=evidence.get("source_text"),
        confidence=_confidence(evidence),
    )
    return {**evidence, **{key: value for key, value in contextual.items() if key != "source_text"}}


def _source_text(value: dict[str, Any]) -> object | None:
    for key in (
        "source_text",
        "description",
        "service_description",
        "display_name",
        "field_name",
        "value",
        "date_local",
    ):
        candidate = value.get(key)
        if candidate not in (None, ""):
            return candidate
    return None


def _confidence(value: dict[str, Any]) -> float | None:
    candidate = value.get("confidence")
    if isinstance(candidate, int | float):
        return float(candidate)
    return None
