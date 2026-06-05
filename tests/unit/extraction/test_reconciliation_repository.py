from __future__ import annotations

from datetime import date
from typing import Any, cast
from uuid import uuid4

from lib.extraction import reconciliation_repository as repo
from lib.extraction.models import (
    CandidateFact,
    ExtractionSourceDocument,
    GatewayExtraction,
    LineItemCandidateFact,
    ObservationCandidateFact,
    PersistedExtraction,
    ValidationReport,
)
from lib.extraction.region_envelope import (
    EvidenceRef,
    RegionExtractionEnvelope,
    RegionFact,
    RegionLineItem,
)


def test_maybe_reconcile_semantic_annotation_persists_document_observation_aggregate(
    monkeypatch,
) -> None:
    document_id = uuid4()
    semantic_annotation_id = uuid4()
    region_id = uuid4()
    extraction_id = uuid4()
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_annotation_id=str(semantic_annotation_id),
        semantic_region_id=str(region_id),
        page_number=1,
        element_id="el-1",
        source_engine="granite_vision_3b",
    )
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_annotation_id=str(semantic_annotation_id),
        semantic_region_id=str(region_id),
        resolved_document_type="real_estate_title",
        semantic_type="generic_form_kvp",
        target_schema="document_observation",
        model_output_schema_name="granite_generic_kvp.v1",
        observations=[
            RegionFact(
                name="real_estate_title.property.address",
                value="123 Main St",
                value_type="string",
                confidence=0.77,
                evidence=[evidence],
            )
        ],
    )
    captured: dict[str, Any] = {}

    monkeypatch.setattr(repo, "db_connection", lambda: _FakeConnection())
    monkeypatch.setattr(repo, "_expected_region_job_count", lambda *args, **kwargs: 1)
    monkeypatch.setattr(
        repo,
        "_current_region_extraction_rows",
        lambda *args, **kwargs: [
            {
                "id": extraction_id,
                "source_semantic_region_id": region_id,
                "semantic_type": "generic_form_kvp",
                "normalized_json": {
                    "schema_name": "document_observation",
                    "observations": [{"field_name": "raw_unanchored", "value": "ignored"}],
                },
                "normalization_json": {
                    "regionEnvelope": envelope.model_dump(mode="json", exclude_none=True)
                },
            }
        ],
    )
    monkeypatch.setattr(repo, "_current_document_extraction_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(repo, "load_extraction_source", lambda _: _source(document_id))
    monkeypatch.setattr(
        repo,
        "persist_extraction_run",
        lambda *args, **kwargs: _capture_persist(captured, *args, **kwargs),
    )

    persisted = repo.maybe_reconcile_semantic_annotation(
        document_id=document_id,
        semantic_annotation_id=semantic_annotation_id,
        schema_name="document_observation",
    )

    assert persisted is not None
    extraction = cast(GatewayExtraction, captured["extraction"])
    validation = cast(ValidationReport, captured["validation"])
    observation_candidates = cast(
        list[ObservationCandidateFact],
        captured["observation_candidates"],
    )
    aggregate = extraction.normalized_json
    assert aggregate["schema_name"] == "document_observation"
    assert aggregate["observations"][0]["field_name"] == "property.address"
    assert validation.needs_review is True
    assert len(observation_candidates) == 1
    assert observation_candidates[0].field_name == "property.address"
    assert captured["field_candidates"] == []
    assert captured["line_item_candidates"] == []


def test_maybe_reconcile_semantic_annotation_rejects_raw_only_invoice_regions(
    monkeypatch,
) -> None:
    document_id = uuid4()
    semantic_annotation_id = uuid4()
    region_id = uuid4()

    monkeypatch.setattr(repo, "db_connection", lambda: _FakeConnection())
    monkeypatch.setattr(repo, "_expected_region_job_count", lambda *args, **kwargs: 1)
    monkeypatch.setattr(
        repo,
        "_current_region_extraction_rows",
        lambda *args, **kwargs: [
            {
                "id": uuid4(),
                "source_semantic_region_id": region_id,
                "semantic_type": "invoice_line_item_table",
                "normalized_json": {
                    "schema_name": "invoice",
                    "line_items": [
                        {
                            "description": "Raw fallback service",
                            "amount": {"amount": 42.0, "currency": "USD"},
                        }
                    ],
                    "totals": {"total": {"amount": 42.0, "currency": "USD"}},
                },
                "normalization_json": {},
            }
        ],
    )
    monkeypatch.setattr(repo, "_current_document_extraction_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(repo, "load_extraction_source", lambda _: _source(document_id))
    monkeypatch.setattr(
        repo,
        "persist_extraction_run",
        lambda *args, **kwargs: PersistedExtraction(
            extraction_id=uuid4(),
            review_status="needs_review",
            candidate_count=0,
            canonical_count=0,
            review_task_count=0,
        ),
    )

    persisted = repo.maybe_reconcile_semantic_annotation(
        document_id=document_id,
        semantic_annotation_id=semantic_annotation_id,
        schema_name="invoice",
    )

    assert persisted is None


def test_maybe_reconcile_semantic_annotation_persists_medical_eob_claim_aggregate(
    monkeypatch,
) -> None:
    document_id = uuid4()
    semantic_annotation_id = uuid4()
    region_id = uuid4()
    extraction_id = uuid4()
    table_id = uuid4()
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_annotation_id=str(semantic_annotation_id),
        semantic_region_id=str(region_id),
        page_number=2,
        table_id=str(table_id),
        row_index=4,
        source_engine="granite_vision_3b",
    )
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_annotation_id=str(semantic_annotation_id),
        semantic_region_id=str(region_id),
        resolved_document_type="medical_eob",
        semantic_type="covered_services_line_item_table",
        target_schema="medical_eob",
        model_output_schema_name="granite_medical_service_lines.v1",
        facts=[
            RegionFact(
                name="medical_eob.payer.display_name",
                value="Anthem Blue Cross",
                value_type="string",
                confidence=0.9,
                evidence=[evidence],
            ),
            RegionFact(
                name="medical_eob.patient.display_name",
                value="Jane Patient",
                value_type="string",
                confidence=0.9,
                evidence=[evidence],
            ),
            RegionFact(
                name="medical_eob.claim_number",
                value="CLM-123",
                value_type="string",
                confidence=0.86,
                evidence=[evidence],
            ),
            RegionFact(
                name="medical_eob.total_patient_responsibility",
                value={"amount": 62.0, "currency": "USD"},
                value_type="money",
                confidence=0.88,
                evidence=[evidence],
            ),
        ],
        line_items=[
            RegionLineItem(
                description="Office visit",
                code="99213",
                quantity=1.0,
                gross_amount=120.0,
                net_amount=62.0,
                currency_code="USD",
                service_date="2026-01-01",
                evidence=[evidence],
                table_id=str(table_id),
                row_index=4,
                page_number=2,
            )
        ],
    )
    captured: dict[str, Any] = {}

    monkeypatch.setattr(repo, "db_connection", lambda: _FakeConnection())
    monkeypatch.setattr(repo, "_expected_region_job_count", lambda *args, **kwargs: 1)
    monkeypatch.setattr(
        repo,
        "_current_region_extraction_rows",
        lambda *args, **kwargs: [
            {
                "id": extraction_id,
                "source_semantic_region_id": region_id,
                "semantic_type": "covered_services_line_item_table",
                "normalized_json": {
                    "schema_name": "medical_eob",
                    "service_lines": [
                        {
                            "service_description": "Raw payload should not drive aggregate",
                            "patient_responsibility": {
                                "amount": 999.0,
                                "currency": "USD",
                            },
                        }
                    ],
                },
                "normalization_json": {
                    "regionEnvelope": envelope.model_dump(mode="json", exclude_none=True)
                },
            }
        ],
    )
    monkeypatch.setattr(repo, "_current_document_extraction_json", lambda *args, **kwargs: {})
    monkeypatch.setattr(repo, "load_extraction_source", lambda _: _source(document_id))
    monkeypatch.setattr(
        repo,
        "persist_extraction_run",
        lambda *args, **kwargs: _capture_persist(captured, *args, **kwargs),
    )

    persisted = repo.maybe_reconcile_semantic_annotation(
        document_id=document_id,
        semantic_annotation_id=semantic_annotation_id,
        schema_name="medical_eob",
    )

    assert persisted is not None
    extraction = cast(GatewayExtraction, captured["extraction"])
    field_candidates = cast(list[CandidateFact], captured["field_candidates"])
    line_item_candidates = cast(list[LineItemCandidateFact], captured["line_item_candidates"])
    aggregate = extraction.normalized_json
    assert aggregate["schema_name"] == "medical_eob"
    assert aggregate["payer"] == {"display_name": "Anthem Blue Cross"}
    assert aggregate["patient"] == {"display_name": "Jane Patient"}
    assert aggregate["claim"] == {"claim_number": "CLM-123"}
    assert aggregate["financial_summary"] == {
        "total_patient_responsibility": {"amount": 62.0, "currency": "USD"}
    }
    assert aggregate["service_lines"][0]["service_description"] == "Office visit"
    assert aggregate["service_lines"][0]["patient_responsibility"] == {
        "amount": 62.0,
        "currency": "USD",
    }
    assert aggregate["service_lines"][0]["ordinal"] == 1
    assert aggregate["metadata"]["quality_outcome"] == "extracted_cleanly"
    assert aggregate["metadata"]["claim_resolution_decisions"]
    assert {candidate.field_path for candidate in field_candidates} >= {
        "medical_eob.payer.display_name",
        "medical_eob.patient.display_name",
        "medical_eob.claim_number",
        "medical_eob.total_patient_responsibility",
    }
    assert len(line_item_candidates) == 1


class _FakeConnection:
    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return _FakeCursor()


class _FakeCursor:
    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _source(document_id):
    return ExtractionSourceDocument(
        document_id=document_id,
        household_id=uuid4(),
        title="Test",
        original_filename="test.pdf",
        mime_type="application/pdf",
        family="real_estate_title",
        subtype=None,
        sensitivity="standard",
        document_date=date(2026, 1, 1),
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[],
        elements=[],
        tables=[],
    )


def _capture_persist(captured, extraction, **kwargs):
    captured["extraction"] = extraction
    captured.update(kwargs)
    return PersistedExtraction(
        extraction_id=uuid4(),
        review_status="needs_review",
        candidate_count=len(kwargs["observation_candidates"]),
        canonical_count=0,
        review_task_count=len(kwargs["observation_candidates"]),
    )
