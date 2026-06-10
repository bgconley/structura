"""Deterministic KVP extraction from selected spans (ADR 0006, E2).

Selected spans become claims verbatim: the value text is the span's exact
element text, parsed with the shared deterministic parsers, anchored to the
span's element/text-span. Expected keys that exactly match a claim-registry
field projection (normalized snake form of the field name or canonical-key
tail) mint family facts under the canonical key; everything else stays a
dot-less observation key for the document_observation lanes. Unmatched keys
remain absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lib.extraction.claim_registry import CLAIM_FAMILY_REGISTRIES
from lib.extraction.expected_field_coverage import normalized_field_name
from lib.extraction.model_output_value_parsing import parse_decimal_text
from lib.extraction.models import ExtractionSourceDocument
from lib.extraction.region_envelope import (
    EvidenceRef,
    RegionExtractionEnvelope,
    RegionFact,
)
from lib.extraction.text_lane.span_candidates import SpanCandidate
from lib.extraction.text_lane.span_selection import SpanSelection
from lib.semantic_annotations.models import SemanticExtractionTask

TEXT_LANE_KVP_METHOD = "text_lane_kvp.v1"


@dataclass(frozen=True)
class KvpLaneExtraction:
    envelope: RegionExtractionEnvelope
    fact_count: int
    observation_count: int
    unmatched_key_count: int


def extract_kvp_region(
    *,
    source: ExtractionSourceDocument,
    semantic_task: SemanticExtractionTask,
    spans: list[SpanCandidate],
    selection: SpanSelection,
    family: str,
    target_schema: str,
) -> KvpLaneExtraction:
    spans_by_id = {span.span_id: span for span in spans}
    facts: list[RegionFact] = []
    observations: list[RegionFact] = []
    unmatched = 0
    for key, span_id in sorted(selection.selections.items()):
        span = spans_by_id.get(span_id) if span_id is not None else None
        if span is None:
            unmatched += 1
            continue
        registry_match = _registry_projection_for_key(family, key)
        if registry_match is not None:
            canonical_key, value_types = registry_match
            fact = _fact_for_span(
                span,
                source=source,
                semantic_task=semantic_task,
                name=canonical_key,
                allowed_value_types=value_types,
            )
            if fact is not None:
                facts.append(fact)
            else:
                unmatched += 1
            continue
        observation = _fact_for_span(
            span,
            source=source,
            semantic_task=semantic_task,
            name=key,
            allowed_value_types=None,
        )
        if observation is not None:
            observations.append(observation)
        else:
            unmatched += 1
    envelope = RegionExtractionEnvelope(
        document_id=str(source.document_id),
        semantic_annotation_id=str(semantic_task.annotation_id),
        semantic_region_id=str(semantic_task.region_id),
        resolved_document_type=family,
        semantic_type=semantic_task.semantic_type,
        target_schema=target_schema,
        model_output_schema_name=TEXT_LANE_KVP_METHOD,
        coverage={
            "lane": "text",
            "page_number": _grounded_page_number(spans),
            "span_candidate_count": len(spans),
            "expected_key_count": len(selection.selections),
            "fact_count": len(facts),
            "observation_count": len(observations),
            "unmatched_key_count": unmatched,
            "selections": selection.selections_json(),
            "labeling": {
                "model_name": selection.model_name,
                "model_version": selection.model_version,
                "prompt_version": selection.prompt_version,
                "from_cache": selection.from_cache,
            },
        },
        facts=facts,
        observations=observations,
        warnings=(["text_lane_kvp_produced_no_values"] if not facts and not observations else []),
    )
    return KvpLaneExtraction(
        envelope=envelope,
        fact_count=len(facts),
        observation_count=len(observations),
        unmatched_key_count=unmatched,
    )


def _registry_projection_for_key(
    family: str,
    expected_key: str,
) -> tuple[str, tuple[str, ...]] | None:
    """Exact normalized match of an expected key to a registry field projection.

    Matching is deliberately stricter than coverage telemetry: claim names
    decide canonical identity, so only exact normalized forms of the
    projection field name, the canonical key without its family prefix, or
    its final segment qualify.
    """
    registry = CLAIM_FAMILY_REGISTRIES.get(family)
    if registry is None:
        return None
    normalized = normalized_field_name(expected_key)
    for projection in registry.field_projections:
        segments = projection.canonical_key.split(".")
        forms = {
            normalized_field_name(projection.field_name),
            normalized_field_name("_".join(segments[1:])),
            normalized_field_name(segments[-1]),
        }
        if normalized in forms:
            return projection.canonical_key, projection.value_types
    return None


def _fact_for_span(
    span: SpanCandidate,
    *,
    source: ExtractionSourceDocument,
    semantic_task: SemanticExtractionTask,
    name: str,
    allowed_value_types: tuple[str, ...] | None,
) -> RegionFact | None:
    value_type, value = _typed_span_value(span, allowed_value_types)
    if value is None:
        return None
    return RegionFact(
        name=name,
        value=value,
        value_type=value_type,  # type: ignore[arg-type]
        evidence=[
            EvidenceRef(
                document_id=str(source.document_id),
                semantic_annotation_id=str(semantic_task.annotation_id),
                semantic_region_id=str(semantic_task.region_id),
                page_number=span.page_number,
                page_id=span.page_id,
                element_id=span.element_id,
                bbox=span.bbox,
                text_span=dict(span.text_span) if span.text_span is not None else None,
                source_text=span.value_text,
                source_engine="docling",
            )
        ],
        source_text=span.value_text,
        source_payload={
            "span_id": span.span_id,
            "span_kind": span.kind,
            "label": span.label_text,
            "method": TEXT_LANE_KVP_METHOD,
        },
    )


def _typed_span_value(
    span: SpanCandidate,
    allowed_value_types: tuple[str, ...] | None,
) -> tuple[str, Any | None]:
    """Deterministic typing for a span value under the target's constraints.

    Registry money/date targets parse strictly (unparseable text yields no
    fact rather than a wrongly-typed claim); observation targets keep the
    span's own typed guess with verbatim text fallback.
    """
    text = span.value_text.strip()
    if not text:
        return ("string", None)
    if allowed_value_types is not None:
        if "money" in allowed_value_types:
            amount = parse_decimal_text(text)
            return ("money", {"amount": amount} if amount is not None else None)
        if "date" in allowed_value_types:
            return ("date", text)
        return ("string", text)
    if span.value_type == "money":
        amount = parse_decimal_text(text)
        if amount is not None:
            return ("money", {"amount": amount})
        return ("string", text)
    if span.value_type == "date":
        return ("date", text)
    return ("string", text)


def _grounded_page_number(spans: list[SpanCandidate]) -> int | None:
    return spans[0].page_number if spans else None
