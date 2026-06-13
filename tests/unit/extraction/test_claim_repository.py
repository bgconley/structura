from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from lib.extraction.claim_aggregate_reconciliation import resolve_claim_regions_for_family
from lib.extraction.claim_candidates import (
    field_candidates_from_claims,
    line_item_candidates_from_claims,
    observation_candidates_from_claims,
)
from lib.extraction.claim_projection import project_claim_family_payload
from lib.extraction.claim_repository import (
    claim_from_row,
    claims_from_rows,
    persist_extraction_claims,
)
from lib.extraction.claims import claims_from_region_envelope
from lib.extraction.models import ExtractionRunScope, ValidationReport
from lib.extraction.region_envelope import (
    EvidenceRef,
    RegionExtractionEnvelope,
    RegionFact,
    RegionLineItem,
)
from lib.extraction.region_reconciliation import RegionExtraction


def test_persist_extraction_claims_records_claim_currency_with_scope_lineage() -> None:
    document_id = uuid4()
    extraction_id = uuid4()
    annotation_id = uuid4()
    region_id = uuid4()
    envelope = _invoice_envelope(
        document_id=document_id,
        annotation_id=annotation_id,
        region_id=region_id,
    )
    claims = claims_from_region_envelope(envelope)
    cursor = RecordingCursor()

    persist_extraction_claims(
        cursor,
        extraction_id=extraction_id,
        claims=claims,
        run_scope=ExtractionRunScope.semantic_region(
            semantic_annotation_id=annotation_id,
            source_semantic_region_id=region_id,
            semantic_type="invoice_line_item_table",
            granite_task="table",
            region_envelope_version="phase8_5-region-envelope-v1",
        ),
    )

    assert len(cursor.executemany_calls) == 1
    sql, params = cursor.executemany_calls[0]
    assert "INSERT INTO extraction_claims" in sql
    assert "ON CONFLICT (extraction_id, claim_id)" in sql
    assert "raw_output" not in sql.lower()
    assert "normalized_json" not in sql
    assert len(params) == len(claims)
    first = params[0]
    assert first[0] == extraction_id
    assert first[1] == document_id
    assert first[3] == annotation_id
    assert first[4] == region_id
    assert first[5] == "invoice_line_item_table"
    assert first[6] == "table"
    assert first[8] == "phase8_5-region-envelope-v1"
    assert first[10] == "invoice.invoice_number"


def test_claim_rows_reconstruct_projection_inputs_without_model_output_payloads() -> None:
    document_id = uuid4()
    extraction_id = uuid4()
    annotation_id = uuid4()
    invoice_region_id = uuid4()
    observation_region_id = uuid4()
    invoice_envelope = _invoice_envelope(
        document_id=document_id,
        annotation_id=annotation_id,
        region_id=invoice_region_id,
    )
    observation_envelope = _observation_envelope(
        document_id=document_id,
        annotation_id=annotation_id,
        region_id=observation_region_id,
    )
    validation = ValidationReport(needs_review=True, checks=[])
    original_invoice_claims = claims_from_region_envelope(invoice_envelope)
    original_observation_claims = claims_from_region_envelope(observation_envelope)

    reconstructed_invoice_claims = claims_from_rows(
        [
            _row_from_claim(claim, extraction_id=extraction_id, region_id=invoice_region_id)
            for claim in original_invoice_claims
        ]
    )
    reconstructed_observation_claims = claims_from_rows(
        [
            _row_from_claim(claim, extraction_id=extraction_id, region_id=observation_region_id)
            for claim in original_observation_claims
        ]
    )

    assert (
        claim_from_row(
            _row_from_claim(
                original_invoice_claims[0],
                extraction_id=extraction_id,
                region_id=invoice_region_id,
            )
        ).as_json()
        == original_invoice_claims[0].as_json()
    )
    field_candidates = field_candidates_from_claims(
        document_id=document_id,
        family="invoice",
        claims=reconstructed_invoice_claims,
        validation=validation,
        source_engine="docling",
        require_concrete_evidence=True,
    )
    line_item_candidates = line_item_candidates_from_claims(
        family="invoice",
        claims=reconstructed_invoice_claims,
        validation=validation,
        source_engine="docling",
        require_concrete_evidence=True,
    )
    observation_candidates = observation_candidates_from_claims(
        family="document_observation",
        claims=reconstructed_observation_claims,
        validation=validation,
        require_concrete_evidence=True,
    )

    assert [claim.as_json() for claim in reconstructed_invoice_claims] == [
        claim.as_json() for claim in original_invoice_claims
    ]
    assert [claim.as_json() for claim in reconstructed_observation_claims] == [
        claim.as_json() for claim in original_observation_claims
    ]
    assert [(c.field_path, c.value, c.evidence) for c in field_candidates] == [
        ("invoice.invoice_number", "INV-100", field_candidates[0].evidence)
    ]
    assert [(c.description, c.net_amount, c.evidence) for c in line_item_candidates] == [
        ("600 mile service", 250.0, line_item_candidates[0].evidence)
    ]
    assert [
        (c.observation_family, c.field_name, c.value, c.evidence) for c in observation_candidates
    ] == [("property", "address", "123 Main St", observation_candidates[0].evidence)]

    aggregate_projection = resolve_claim_regions_for_family(
        family="invoice",
        missing_claims_reason="no_claims",
        regions=[
            RegionExtraction(
                extraction_id=extraction_id,
                semantic_region_id=invoice_region_id,
                semantic_type="invoice_line_item_table",
                region_envelope=None,
                claims=tuple(reconstructed_invoice_claims),
            )
        ],
    )
    assert aggregate_projection is not None
    payload = project_claim_family_payload(
        document_id=document_id,
        created_at=datetime(2026, 6, 13, tzinfo=UTC),
        projection=aggregate_projection.claim_projection,
        metadata=aggregate_projection.metadata,
    )
    assert payload is not None
    assert payload["invoice"]["invoice_number"] == "INV-100"
    assert payload["line_items"][0]["description"] == "600 mile service"


def _invoice_envelope(
    *,
    document_id: UUID,
    annotation_id: UUID,
    region_id: UUID,
) -> RegionExtractionEnvelope:
    line_evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_annotation_id=str(annotation_id),
        semantic_region_id=str(region_id),
        page_number=1,
        table_id="invoice-lines",
        row_index=2,
        source_engine="docling",
    )
    fact_evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_annotation_id=str(annotation_id),
        semantic_region_id=str(region_id),
        page_number=1,
        element_id="invoice-number-label",
        source_engine="docling",
        source_text="Invoice # INV-100",
    )
    return RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_annotation_id=str(annotation_id),
        semantic_region_id=str(region_id),
        resolved_document_type="invoice",
        semantic_type="invoice_line_item_table",
        target_schema="invoice",
        model_output_schema_name="docling_text_table.v1",
        facts=[
            RegionFact(
                name="invoice.invoice_number",
                value="INV-100",
                value_type="string",
                confidence=0.98,
                source_text="Invoice # INV-100",
                evidence=[fact_evidence],
            )
        ],
        line_items=[
            RegionLineItem(
                description="600 mile service",
                net_amount=250.0,
                currency_code="USD",
                evidence=[line_evidence],
                table_id="invoice-lines",
                row_index=2,
                page_number=1,
            )
        ],
    )


def _observation_envelope(
    *,
    document_id: UUID,
    annotation_id: UUID,
    region_id: UUID,
) -> RegionExtractionEnvelope:
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_annotation_id=str(annotation_id),
        semantic_region_id=str(region_id),
        page_number=1,
        element_id="property-address",
        source_engine="docling",
        source_text="Property Address: 123 Main St",
    )
    return RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_annotation_id=str(annotation_id),
        semantic_region_id=str(region_id),
        resolved_document_type="real_estate_title",
        semantic_type="generic_form_kvp",
        target_schema="document_observation",
        model_output_schema_name="docling_text_kvp.v1",
        observations=[
            RegionFact(
                name="property.address",
                value="123 Main St",
                value_type="string",
                confidence=0.88,
                source_text="Property Address: 123 Main St",
                evidence=[evidence],
            )
        ],
    )


def _row_from_claim(claim, *, extraction_id: UUID, region_id: UUID) -> dict[str, object]:
    return {
        "extraction_id": extraction_id,
        "claim_id": claim.claim_id,
        "document_id": UUID(claim.document_id),
        "source_engine": claim.source_engine,
        "semantic_annotation_id": uuid4(),
        "source_semantic_region_id": region_id,
        "semantic_type": "invoice_line_item_table",
        "granite_task": "table",
        "method": claim.method,
        "region_envelope_version": "phase8_5-region-envelope-v1",
        "canonical_key": claim.canonical_key,
        "raw_value": claim.raw_value,
        "typed_value_json": claim.typed_value,
        "value_type": claim.value_type,
        "confidence": claim.confidence,
        "group_id": claim.group_id,
        "anchor_json": claim.anchor.as_json(),
        "evidence_json": list(claim.evidence),
        "metadata_json": {},
    }


class RecordingCursor:
    def __init__(self) -> None:
        self.executemany_calls: list[tuple[str, list[tuple[object, ...]]]] = []

    def executemany(self, sql: str, params: list[tuple[object, ...]]) -> None:
        self.executemany_calls.append((sql, params))
