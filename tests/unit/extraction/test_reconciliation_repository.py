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


def test_current_region_extraction_rows_keeps_raw_payload_out_of_reconciliation_loader() -> None:
    class RecordingCursor:
        query = ""
        args: tuple[object, ...] = ()

        def execute(self, query: str, args: tuple[object, ...]) -> None:
            self.query = query
            self.args = args

        def fetchall(self) -> list[dict[str, object]]:
            return []

    cursor = RecordingCursor()

    rows = repo._current_region_extraction_rows(
        cursor,
        document_id=uuid4(),
        semantic_annotation_id=uuid4(),
        schema_name="invoice",
    )

    assert rows == []
    assert "normalization_json" in cursor.query
    assert "normalized_json" not in cursor.query


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
    monkeypatch.setattr(repo, "_region_job_status_counts", lambda *args, **kwargs: {"succeeded": 1})
    monkeypatch.setattr(repo, "_current_aggregate_region_fingerprint", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        repo,
        "_plan_skipped_task_summary",
        lambda *args, **kwargs: {"skipped_task_count": 0, "skipped_tasks": []},
    )
    monkeypatch.setattr(
        repo,
        "_current_region_extraction_rows",
        lambda *args, **kwargs: [
            {
                "id": extraction_id,
                "source_semantic_region_id": region_id,
                "semantic_type": "generic_form_kvp",
                "normalization_json": {
                    "regionEnvelope": envelope.model_dump(mode="json", exclude_none=True)
                },
            }
        ],
    )
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


def test_reconcile_current_regions_skips_region_job_status_gate(monkeypatch) -> None:
    document_id = uuid4()
    semantic_annotation_id = uuid4()
    region_id = uuid4()
    extraction_id = uuid4()
    envelope = _receipt_envelope_for_reconciliation(document_id, semantic_annotation_id, region_id)
    captured = _patch_reconciliation_helpers(
        monkeypatch,
        envelope=envelope,
        extraction_id=extraction_id,
        semantic_type="receipt_line_item_table",
        job_counts={"failed": 1},
    )

    def fail_if_region_jobs_are_read(*_args, **_kwargs):
        raise AssertionError("document orchestration must not wait on region job status")

    monkeypatch.setattr(repo, "_region_job_status_counts", fail_if_region_jobs_are_read)

    persisted = repo.reconcile_semantic_annotation_from_current_regions(
        document_id=document_id,
        semantic_annotation_id=semantic_annotation_id,
        schema_name="receipt",
    )

    assert persisted is not None
    extraction = cast(GatewayExtraction, captured["extraction"])
    assert extraction.schema_name == "receipt"
    assert extraction.normalized_json["metadata"]["region_job_coverage"]["expected_jobs"] == 1


def test_maybe_reconcile_semantic_annotation_rejects_region_without_claims(
    monkeypatch,
) -> None:
    document_id = uuid4()
    semantic_annotation_id = uuid4()
    region_id = uuid4()

    monkeypatch.setattr(repo, "db_connection", lambda: _FakeConnection())
    monkeypatch.setattr(repo, "_region_job_status_counts", lambda *args, **kwargs: {"succeeded": 1})
    monkeypatch.setattr(repo, "_current_aggregate_region_fingerprint", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        repo,
        "_plan_skipped_task_summary",
        lambda *args, **kwargs: {"skipped_task_count": 0, "skipped_tasks": []},
    )
    monkeypatch.setattr(
        repo,
        "_current_region_extraction_rows",
        lambda *args, **kwargs: [
            {
                "id": uuid4(),
                "source_semantic_region_id": region_id,
                "semantic_type": "invoice_line_item_table",
                "normalization_json": {},
            }
        ],
    )
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
    monkeypatch.setattr(repo, "_region_job_status_counts", lambda *args, **kwargs: {"succeeded": 1})
    monkeypatch.setattr(repo, "_current_aggregate_region_fingerprint", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        repo,
        "_plan_skipped_task_summary",
        lambda *args, **kwargs: {"skipped_task_count": 0, "skipped_tasks": []},
    )
    monkeypatch.setattr(
        repo,
        "_current_region_extraction_rows",
        lambda *args, **kwargs: [
            {
                "id": extraction_id,
                "source_semantic_region_id": region_id,
                "semantic_type": "covered_services_line_item_table",
                "normalization_json": {
                    "regionEnvelope": envelope.model_dump(mode="json", exclude_none=True)
                },
            }
        ],
    )
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


def test_maybe_reconcile_semantic_annotation_persists_service_record_observation_aggregate(
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
        table_id="service-table",
        row_index=2,
        source_engine="granite_vision_3b",
    )
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_annotation_id=str(semantic_annotation_id),
        semantic_region_id=str(region_id),
        resolved_document_type="service_record",
        semantic_type="service_record_line_item_table",
        target_schema="receipt",
        model_output_schema_name="granite_service_record_line_items.v1",
        line_items=[
            RegionLineItem(
                description="600 mile running-in check",
                quantity=1.0,
                unit_price=185.0,
                net_amount=185.0,
                currency_code="USD",
                category_hint="service",
                evidence=[evidence],
                table_id="service-table",
                row_index=2,
                page_number=1,
            )
        ],
    )
    captured: dict[str, Any] = {}

    monkeypatch.setattr(repo, "db_connection", lambda: _FakeConnection())
    monkeypatch.setattr(repo, "_region_job_status_counts", lambda *args, **kwargs: {"succeeded": 1})
    monkeypatch.setattr(repo, "_current_aggregate_region_fingerprint", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        repo,
        "_plan_skipped_task_summary",
        lambda *args, **kwargs: {"skipped_task_count": 0, "skipped_tasks": []},
    )
    monkeypatch.setattr(
        repo,
        "_current_region_extraction_rows",
        lambda *args, **kwargs: [
            {
                "id": extraction_id,
                "source_semantic_region_id": region_id,
                "semantic_type": "service_record_line_item_table",
                "normalization_json": {
                    "regionEnvelope": envelope.model_dump(mode="json", exclude_none=True)
                },
            }
        ],
    )
    monkeypatch.setattr(repo, "load_extraction_source", lambda _: _source(document_id))
    monkeypatch.setattr(
        repo,
        "persist_extraction_run",
        lambda *args, **kwargs: _capture_persist(captured, *args, **kwargs),
    )

    persisted = repo.maybe_reconcile_semantic_annotation(
        document_id=document_id,
        semantic_annotation_id=semantic_annotation_id,
        schema_name="receipt",
        canonical_target_schema="service_record",
    )

    assert persisted is not None
    extraction = cast(GatewayExtraction, captured["extraction"])
    observation_candidates = cast(
        list[ObservationCandidateFact],
        captured["observation_candidates"],
    )
    aggregate = extraction.normalized_json
    assert extraction.schema_name == "document_observation"
    assert aggregate["schema_name"] == "document_observation"
    assert aggregate["metadata"]["source_families"] == ["service_record"]
    assert aggregate["metadata"]["source_schema_name"] == "receipt"
    evidence_ref = [
        {
            "document_id": str(document_id),
            "semantic_annotation_id": str(semantic_annotation_id),
            "semantic_region_id": str(region_id),
            "page_number": 1,
            "table_id": "service-table",
            "source_engine": "granite_vision_3b",
            "row_index": 2,
        }
    ]
    observations_by_field = {item["field_name"]: item for item in aggregate["observations"]}
    assert set(observations_by_field) == {
        "line_item.amount",
        "line_item.category_hint",
        "line_item.description",
        "line_item.quantity",
        "line_item.unit_price",
    }
    for observation in observations_by_field.values():
        assert observation["family"] == "service_record"
        assert observation["evidence"] == evidence_ref
        assert "confidence" not in observation
    assert observations_by_field["line_item.description"]["value"] == "600 mile running-in check"
    assert observations_by_field["line_item.category_hint"]["source_text"] == "service"
    assert observations_by_field["line_item.quantity"]["value_type"] == "number"
    assert observations_by_field["line_item.amount"]["value"] == {
        "amount": 185.0,
        "currency": "USD",
    }
    assert (
        observations_by_field["line_item.unit_price"]["source_text"]
        == '{"amount":185.0,"currency":"USD"}'
    )
    assert [candidate.field_name for candidate in observation_candidates] == [
        "line_item.amount",
        "line_item.category_hint",
        "line_item.description",
        "line_item.quantity",
        "line_item.unit_price",
    ]
    assert captured["field_candidates"] == []
    assert captured["line_item_candidates"] == []


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

    def execute(self, *args: object, **kwargs: object) -> None:
        return None

    def fetchone(self) -> None:
        return None

    def fetchall(self) -> list[object]:
        return []


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


def _receipt_envelope_for_reconciliation(
    document_id, semantic_annotation_id, region_id
) -> RegionExtractionEnvelope:
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_annotation_id=str(semantic_annotation_id),
        semantic_region_id=str(region_id),
        page_number=1,
        table_id="receipt-table",
        row_index=1,
        source_engine="granite_vision_3b",
    )
    return RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_annotation_id=str(semantic_annotation_id),
        semantic_region_id=str(region_id),
        resolved_document_type="receipt",
        semantic_type="receipt_line_item_table",
        target_schema="receipt",
        model_output_schema_name="granite_receipt_line_items.v1",
        facts=[
            RegionFact(
                name="receipt.merchant.display_name",
                value="Corner Cafe",
                value_type="string",
                evidence=[evidence],
            ),
            RegionFact(
                name="receipt.transaction.total",
                value={"amount": 5.75},
                value_type="money",
                evidence=[evidence],
            ),
        ],
        line_items=[
            RegionLineItem(
                description="COFFEE",
                quantity=1.0,
                net_amount=5.75,
                evidence=[evidence],
                table_id="receipt-table",
                row_index=1,
                page_number=1,
            )
        ],
    )


def _patch_reconciliation_helpers(
    monkeypatch,
    *,
    envelope: RegionExtractionEnvelope,
    extraction_id,
    semantic_type: str,
    job_counts: dict[str, int],
    existing_fingerprint: list[str] | None = None,
    skipped_task_count: int = 0,
) -> dict[str, Any]:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(repo, "db_connection", lambda: _FakeConnection())
    monkeypatch.setattr(repo, "_region_job_status_counts", lambda *args, **kwargs: dict(job_counts))
    monkeypatch.setattr(
        repo,
        "_current_aggregate_region_fingerprint",
        lambda *args, **kwargs: existing_fingerprint,
    )
    monkeypatch.setattr(
        repo,
        "_plan_skipped_task_summary",
        lambda *args, **kwargs: {
            "skipped_task_count": skipped_task_count,
            "skipped_tasks": (
                [
                    {
                        "status": "skipped_budget_exceeded",
                        "skip_reason": "planner_budget_or_fanout_policy",
                        "count": skipped_task_count,
                    }
                ]
                if skipped_task_count
                else []
            ),
        },
    )
    monkeypatch.setattr(
        repo,
        "_current_region_extraction_rows",
        lambda *args, **kwargs: [
            {
                "id": extraction_id,
                "source_semantic_region_id": envelope.semantic_region_id,
                "semantic_type": semantic_type,
                "normalization_json": {
                    "regionEnvelope": envelope.model_dump(mode="json", exclude_none=True)
                },
            }
        ],
    )
    monkeypatch.setattr(
        repo,
        "load_extraction_source",
        lambda document_id: _source(document_id),
    )
    monkeypatch.setattr(
        repo,
        "persist_extraction_run",
        lambda *args, **kwargs: _capture_persist(captured, *args, **kwargs),
    )
    return captured


def test_maybe_reconcile_persists_receipt_claim_aggregate(monkeypatch) -> None:
    document_id = uuid4()
    semantic_annotation_id = uuid4()
    region_id = uuid4()
    envelope = _receipt_envelope_for_reconciliation(document_id, semantic_annotation_id, region_id)
    captured = _patch_reconciliation_helpers(
        monkeypatch,
        envelope=envelope,
        extraction_id=uuid4(),
        semantic_type="receipt_line_item_table",
        job_counts={"succeeded": 1},
    )

    persisted = repo.maybe_reconcile_semantic_annotation(
        document_id=document_id,
        semantic_annotation_id=semantic_annotation_id,
        schema_name="receipt",
    )

    assert persisted is not None
    extraction = cast(GatewayExtraction, captured["extraction"])
    aggregate = extraction.normalized_json
    assert extraction.schema_name == "receipt"
    assert aggregate["schema_name"] == "receipt"
    assert aggregate["merchant"]["display_name"] == "Corner Cafe"
    assert aggregate["transaction"]["total"] == {"amount": 5.75}
    assert [item["description"] for item in aggregate["line_items"]] == ["COFFEE"]
    assert aggregate["metadata"]["quality_outcome"] in {
        "extracted_cleanly",
        "needs_human_review",
    }


def test_maybe_reconcile_builds_partial_aggregate_after_dead_letter(monkeypatch) -> None:
    document_id = uuid4()
    semantic_annotation_id = uuid4()
    region_id = uuid4()
    envelope = _receipt_envelope_for_reconciliation(document_id, semantic_annotation_id, region_id)
    captured = _patch_reconciliation_helpers(
        monkeypatch,
        envelope=envelope,
        extraction_id=uuid4(),
        semantic_type="receipt_line_item_table",
        job_counts={"succeeded": 1, "dead_letter": 1},
    )

    persisted = repo.maybe_reconcile_semantic_annotation(
        document_id=document_id,
        semantic_annotation_id=semantic_annotation_id,
        schema_name="receipt",
    )

    assert persisted is not None
    extraction = cast(GatewayExtraction, captured["extraction"])
    aggregate = extraction.normalized_json
    coverage = aggregate["metadata"]["region_job_coverage"]
    assert coverage["expected_jobs"] == 2
    assert coverage["dead_letter_jobs"] == 1
    assert coverage["missing_region_jobs"] == 1
    assert aggregate["metadata"]["quality_outcome"] == "needs_human_review"
    validation = cast(ValidationReport, captured["validation"])
    assert validation.needs_review is True
    assert any(
        check.get("code") == "aggregate_region_coverage_incomplete" for check in validation.checks
    )


def test_maybe_reconcile_waits_for_pending_retry_jobs(monkeypatch) -> None:
    document_id = uuid4()
    semantic_annotation_id = uuid4()
    region_id = uuid4()
    envelope = _receipt_envelope_for_reconciliation(document_id, semantic_annotation_id, region_id)
    _patch_reconciliation_helpers(
        monkeypatch,
        envelope=envelope,
        extraction_id=uuid4(),
        semantic_type="receipt_line_item_table",
        job_counts={"succeeded": 1, "failed": 1},
    )

    assert (
        repo.maybe_reconcile_semantic_annotation(
            document_id=document_id,
            semantic_annotation_id=semantic_annotation_id,
            schema_name="receipt",
        )
        is None
    )


def test_maybe_reconcile_skips_when_aggregate_already_current(monkeypatch) -> None:
    document_id = uuid4()
    semantic_annotation_id = uuid4()
    region_id = uuid4()
    extraction_id = uuid4()
    envelope = _receipt_envelope_for_reconciliation(document_id, semantic_annotation_id, region_id)
    _patch_reconciliation_helpers(
        monkeypatch,
        envelope=envelope,
        extraction_id=extraction_id,
        semantic_type="receipt_line_item_table",
        job_counts={"succeeded": 1},
        existing_fingerprint=[str(extraction_id)],
    )

    assert (
        repo.maybe_reconcile_semantic_annotation(
            document_id=document_id,
            semantic_annotation_id=semantic_annotation_id,
            schema_name="receipt",
        )
        is None
    )


def test_maybe_reconcile_marks_plan_budget_skips_as_incomplete_coverage(monkeypatch) -> None:
    document_id = uuid4()
    semantic_annotation_id = uuid4()
    region_id = uuid4()
    envelope = _receipt_envelope_for_reconciliation(document_id, semantic_annotation_id, region_id)
    captured = _patch_reconciliation_helpers(
        monkeypatch,
        envelope=envelope,
        extraction_id=uuid4(),
        semantic_type="receipt_line_item_table",
        job_counts={"succeeded": 1},
        skipped_task_count=2,
    )

    persisted = repo.maybe_reconcile_semantic_annotation(
        document_id=document_id,
        semantic_annotation_id=semantic_annotation_id,
        schema_name="receipt",
    )

    assert persisted is not None
    extraction = cast(GatewayExtraction, captured["extraction"])
    coverage = extraction.normalized_json["metadata"]["region_job_coverage"]
    assert coverage["plan_skipped_task_count"] == 2
    validation = cast(ValidationReport, captured["validation"])
    assert any(
        check.get("code") == "aggregate_region_coverage_incomplete" for check in validation.checks
    )


def test_maybe_reconcile_treats_in_flight_settled_job_as_succeeded(monkeypatch) -> None:
    document_id = uuid4()
    semantic_annotation_id = uuid4()
    region_id = uuid4()
    settled_job_id = uuid4()
    envelope = _receipt_envelope_for_reconciliation(document_id, semantic_annotation_id, region_id)
    captured = _patch_reconciliation_helpers(
        monkeypatch,
        envelope=envelope,
        extraction_id=uuid4(),
        semantic_type="receipt_line_item_table",
        job_counts={"succeeded": 1},
    )
    seen_kwargs: dict[str, Any] = {}
    original = repo._region_job_status_counts

    def recording_counts(cur, **kwargs):
        seen_kwargs.update(kwargs)
        return {"succeeded": 1}

    del original
    monkeypatch.setattr(repo, "_region_job_status_counts", recording_counts)

    persisted = repo.maybe_reconcile_semantic_annotation(
        document_id=document_id,
        semantic_annotation_id=semantic_annotation_id,
        schema_name="receipt",
        settled_job_id=settled_job_id,
    )

    assert persisted is not None
    assert seen_kwargs.get("settled_job_id") == settled_job_id
    assert captured["extraction"].schema_name == "receipt"


def test_region_job_status_counts_settles_in_flight_job_in_sql() -> None:
    class RecordingCursor:
        query = ""
        args: tuple[object, ...] = ()

        def execute(self, query: str, args: tuple[object, ...]) -> None:
            self.query = query
            self.args = args

        def fetchall(self) -> list[dict[str, object]]:
            return []

    cursor = RecordingCursor()
    settled = uuid4()
    repo._region_job_status_counts(
        cursor,
        document_id=uuid4(),
        semantic_annotation_id=uuid4(),
        schema_name="receipt",
        settled_job_id=settled,
    )
    assert "CASE WHEN id = %s THEN 'succeeded' ELSE status END" in cursor.query
    assert cursor.args[0] == settled
