from __future__ import annotations

from typing import Any

from lib.extraction.evidence_concretizer import (
    attach_evidence_to_envelope,
    concretize_normalized_evidence,
)
from lib.extraction.evidence_context import EvidenceContext
from lib.extraction.region_envelope import (
    REGION_ENVELOPE_VERSION,
    envelope_from_normalization_projection,
    envelope_json,
    to_normalization_projection,
)


def finalized_region_output(
    normalized: dict[str, Any],
    metadata: dict[str, Any],
    wrapper_repairs: list[str],
    evidence_context: EvidenceContext | None,
    *,
    model_output_schema_name: str | None,
    semantic_type: str | None,
    target_schema: str | None,
    resolved_document_type: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    repairs = [*wrapper_repairs, *metadata.get("repairs", [])]
    if evidence_context is not None:
        normalized = concretize_normalized_evidence(normalized, evidence_context)
        repairs.append("attached_region_evidence_context")
    envelope = envelope_from_normalization_projection(
        projection=normalized,
        model_output_schema_name=model_output_schema_name or metadata.get("mapper"),
        semantic_type=semantic_type,
        target_schema=target_schema,
        resolved_document_type=resolved_document_type,
        source_engine=evidence_context.source_engine if evidence_context else None,
    )
    if evidence_context is not None:
        envelope = attach_evidence_to_envelope(envelope=envelope, ctx=evidence_context)
    normalized = to_normalization_projection(envelope)
    metadata["repairs"] = repairs
    metadata["regionEnvelopeVersion"] = REGION_ENVELOPE_VERSION
    metadata["regionEnvelope"] = envelope_json(envelope)
    metadata["normalizedProjectionDerivedFromEnvelope"] = True
    return normalized, metadata
