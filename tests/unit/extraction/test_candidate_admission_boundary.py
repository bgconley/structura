from __future__ import annotations

from uuid import uuid4

from lib.extraction.candidate_admission_boundary import apply_candidate_admission_boundary
from lib.extraction.models import (
    ExtractionRunScope,
    ExtractionSourceDocument,
    GatewayExtraction,
    ModelRoute,
)
from lib.extraction.region_envelope import RegionExtractionEnvelope


def test_semantic_region_envelope_admission_skips_legacy_payload_rejection_scan() -> None:
    document_id = uuid4()
    region_id = uuid4()
    extraction = _extraction(
        normalized_json={
            "schema_name": "receipt",
            "line_items": [
                {
                    "description": "Identify and extract the schema",
                    "quantity": "1.0000",
                    "unit": "rows",
                    "amount": {"amount": 1.0, "currency": "USD"},
                    "evidence": [_evidence(document_id, region_id)],
                }
            ],
        },
        normalization_json={
            "regionEnvelope": RegionExtractionEnvelope(
                document_id=str(document_id),
                semantic_region_id=str(region_id),
                resolved_document_type="receipt",
                semantic_type="receipt_line_item_table",
                target_schema="receipt",
                model_output_schema_name="granite_receipt_line_items.v1",
            ).model_dump(mode="json", exclude_none=True)
        },
    )

    result = apply_candidate_admission_boundary(
        extraction=extraction,
        source=_source(document_id),
        run_scope=ExtractionRunScope.semantic_region(
            semantic_annotation_id=uuid4(),
            source_semantic_region_id=region_id,
            semantic_type="receipt_line_item_table",
            granite_task="tables_json",
            canonical_target_schema="receipt",
        ),
        field_candidates=[],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert result.admission.events == []
    assert result.admission.rejected_candidates == []


def test_document_level_admission_still_scans_payload_rejections() -> None:
    document_id = uuid4()
    extraction = _extraction(
        normalized_json={
            "schema_name": "receipt",
            "line_items": [
                {
                    "description": "Identify and extract the schema",
                    "quantity": "1.0000",
                    "unit": "rows",
                    "amount": {"amount": 1.0, "currency": "USD"},
                    "evidence": [_evidence(document_id, uuid4())],
                }
            ],
        },
        normalization_json={},
    )

    result = apply_candidate_admission_boundary(
        extraction=extraction,
        source=_source(document_id),
        run_scope=ExtractionRunScope.document(),
        field_candidates=[],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert [event.decision for event in result.admission.events] == ["rejected_artifact"]
    assert result.admission.rejected_candidates[0]["reasons"] == ["prompt_or_schema_echo"]


def _extraction(
    *,
    normalized_json: dict[str, object],
    normalization_json: dict[str, object],
) -> GatewayExtraction:
    return GatewayExtraction(
        schema_name="receipt",
        schema_version="v1",
        route=ModelRoute(
            source_engine="granite_vision_3b",
            model_name="granite",
            model_version="v1",
            prompt_version="prompt",
            route_profile="docling_plus_granite_structured",
        ),
        normalized_json=normalized_json,
        raw_output_json={"modelInvoked": True},
        model_output_schema_name="granite_receipt_line_items.v1",
        normalization_json=normalization_json,
    )


def _source(document_id) -> ExtractionSourceDocument:
    return ExtractionSourceDocument(
        document_id=document_id,
        household_id=uuid4(),
        title="Test",
        original_filename="test.pdf",
        mime_type="application/pdf",
        family="receipt",
        subtype=None,
        sensitivity="standard",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[],
        elements=[],
        tables=[],
    )


def _evidence(document_id, semantic_region_id) -> dict[str, object]:
    return {
        "document_id": str(document_id),
        "semantic_region_id": str(semantic_region_id),
        "page_number": 1,
        "table_id": "table-1",
        "row_index": 1,
        "source_engine": "granite_vision_3b",
    }
