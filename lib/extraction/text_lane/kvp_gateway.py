"""KVP text-lane extraction gateway (ADR 0006 X2, migration phase E2).

Mirrors the table-lane gateway: deterministic span candidates from the
grounded page, an enum span-selection call, claims born from selected spans,
and the standard GatewayExtraction/RegionExtractionEnvelope persistence
shape. TextLaneAbstention falls back to the vision path with lane telemetry.
"""

from __future__ import annotations

from lib.extraction.contract_registry import resolved_document_type_from_task_metadata
from lib.extraction.models import ExtractionSourceDocument, GatewayExtraction, ModelRoute
from lib.extraction.region_envelope import (
    REGION_ENVELOPE_VERSION,
    envelope_json,
    to_normalization_projection,
)
from lib.extraction.text_lane.eligibility import LaneDecision, grounded_page_number
from lib.extraction.text_lane.gateway import TextLaneAbstention
from lib.extraction.text_lane.kvp_extractor import TEXT_LANE_KVP_METHOD, extract_kvp_region
from lib.extraction.text_lane.span_candidates import span_candidates_for_page
from lib.extraction.text_lane.span_selection import (
    LiveSpanSelector,
    SpanSelector,
    selection_keys,
)
from lib.model_runtime.http_client import ModelProtocolError
from lib.semantic_annotations.models import SemanticExtractionTask


class TextLaneKvpExtractionGateway:
    prompt_version = TEXT_LANE_KVP_METHOD

    def __init__(self, *, selector: SpanSelector | None = None) -> None:
        self.selector = selector or LiveSpanSelector()

    def extract(
        self,
        source: ExtractionSourceDocument,
        *,
        schema_name: str,
        route_profile: str,
        semantic_task: SemanticExtractionTask | None = None,
        lane_decision: LaneDecision | None = None,
    ) -> GatewayExtraction:
        if semantic_task is None:
            raise TextLaneAbstention("no_semantic_task")
        expected_keys = selection_keys(semantic_task.expected_fields)
        if not expected_keys:
            raise TextLaneAbstention("no_expected_fields")
        page_number = grounded_page_number(source, semantic_task)
        if page_number is None:
            raise TextLaneAbstention("no_grounded_page")
        spans = span_candidates_for_page(source, page_number)
        if not spans:
            raise TextLaneAbstention("no_span_candidates")
        family = resolved_document_type_from_task_metadata(
            metadata=semantic_task.metadata,
            semantic_type=semantic_task.semantic_type,
            target_schema=schema_name,
        )
        try:
            selection = self.selector.select_spans(
                family=family,
                expected_keys=expected_keys,
                spans=spans,
            )
        except ModelProtocolError as exc:
            raise TextLaneAbstention(f"span_selection_failed:{exc}") from exc
        if all(span_id is None for span_id in selection.selections.values()):
            raise TextLaneAbstention("all_keys_unmatched")
        extraction = extract_kvp_region(
            source=source,
            semantic_task=semantic_task,
            spans=spans,
            selection=selection,
            family=family,
            target_schema=schema_name,
        )
        if extraction.fact_count == 0 and extraction.observation_count == 0:
            raise TextLaneAbstention("no_extractable_values")
        envelope = extraction.envelope
        normalization_json: dict[str, object] = {
            "mapper": TEXT_LANE_KVP_METHOD,
            "repairs": [],
            "lane": "text",
            "laneEligibility": lane_decision.reason if lane_decision is not None else None,
            "spanSelections": selection.selections_json(),
            "regionEnvelopeVersion": REGION_ENVELOPE_VERSION,
            "regionEnvelope": envelope_json(envelope),
            "normalizedProjectionDerivedFromEnvelope": True,
        }
        raw_output_json: dict[str, object] = {
            "modelInvoked": not selection.from_cache,
            "lane": "text",
            "sourceEngine": "docling",
            "spanSelection": {
                "promptVersion": selection.prompt_version,
                "modelName": selection.model_name,
                "modelVersion": selection.model_version,
                "fromCache": selection.from_cache,
                "selections": selection.selections_json(),
            },
            "pageNumber": page_number,
            "spanCandidateCount": len(spans),
            "factCount": extraction.fact_count,
            "observationCount": extraction.observation_count,
            "unmatchedKeyCount": extraction.unmatched_key_count,
        }
        return GatewayExtraction(
            schema_name=schema_name,
            schema_version="v1",
            route=ModelRoute(
                source_engine="docling",
                model_name="text-lane-kvp-extractor",
                model_version="e2-v1",
                prompt_version=TEXT_LANE_KVP_METHOD,
                route_profile=route_profile,
            ),
            normalized_json=to_normalization_projection(envelope),
            raw_output_json=raw_output_json,
            model_output_schema_name=TEXT_LANE_KVP_METHOD,
            model_output_schema_version="v1",
            normalization_json=normalization_json,
            metadata={
                "lane": "text",
                "spanSelectionFromCache": selection.from_cache,
            },
        )
