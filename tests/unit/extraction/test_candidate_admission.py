from __future__ import annotations

import json
from datetime import date
from typing import Any, cast
from uuid import uuid4

from lib.extraction.candidate_admission import (
    CANDIDATE_GATE_VERSION,
    CandidateAdmissionContext,
    admit_extraction_candidates,
    persist_candidate_admission_events,
    rejected_candidates_from_payload,
)
from lib.extraction.contract_registry import CONTRACT_REGISTRY_VERSION
from lib.extraction.models import (
    CandidateFact,
    ExtractionRunScope,
    LineItemCandidateFact,
    ObservationCandidateFact,
)


def test_prompt_echo_line_item_is_rejected_and_not_admitted() -> None:
    context = _context()
    candidate = LineItemCandidateFact(
        line_item_type="receipt_item",
        ordinal=1,
        description="Identify and extract the schema of all tables in the image",
        quantity=1.0,
        unit="rows",
        unit_price=1.0,
        gross_amount=1.0,
        net_amount=1.0,
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[candidate],
        observation_candidates=[],
    )

    assert admission.line_item_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_artifact": 1},
    }
    assert admission.events[0].decision == "rejected_artifact"
    assert admission.events[0].reasons == ("prompt_or_schema_echo",)


def test_schema_artifact_key_field_is_rejected_and_not_admitted() -> None:
    context = _context()
    candidate = CandidateFact(
        field_path="receipt.transaction.total",
        value_type="json",
        value={"$schema": "receipt.v1", "amount": 4.65},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.events[0].decision == "rejected_artifact"
    assert admission.events[0].reasons == ("prompt_or_schema_echo",)


def test_model_backed_candidates_are_admitted_as_review_required() -> None:
    context = _context()
    candidate = CandidateFact(
        field_path="receipt.transaction.total",
        value_type="money",
        value={"amount": 4.65, "currency": "USD"},
        currency="USD",
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert len(admission.field_candidates) == 1
    assert admission.field_candidates[0].status == "needs_review"
    assert admission.events[0].decision == "admitted_review_required"
    assert admission.events[0].candidate_gate_version == CANDIDATE_GATE_VERSION
    assert admission.events[0].contract_registry_version == CONTRACT_REGISTRY_VERSION


def test_blank_observation_field_name_is_rejected_before_insertion() -> None:
    context = _context()
    candidate = ObservationCandidateFact(
        observation_family="document_observation",
        field_name="   ",
        value_type="string",
        value="visible escrow note",
        evidence=[_evidence(context)],
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[],
        observation_candidates=[candidate],
    )

    assert admission.observation_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_field_name",)


def test_nested_placeholder_field_value_is_rejected_before_insertion() -> None:
    context = _context()
    candidate = CandidateFact(
        field_path="receipt.transaction.total",
        value_type="money",
        value={"amount": "null", "currency": "USD"},
        currency="USD",
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_or_null_value",)


def test_incompatible_field_schema_candidate_is_rejected_before_insertion() -> None:
    context = _context(canonical_target_schema="invoice")
    candidate = CandidateFact(
        field_path="receipt.transaction.total",
        value_type="money",
        value={"amount": 4.65, "currency": "USD"},
        currency="USD",
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.events[0].decision == "rejected_family_schema"
    assert admission.events[0].reasons == ("candidate_schema_incompatible",)


def test_admitted_candidates_carry_admission_fingerprints_for_report_evidence() -> None:
    context = _context()

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[
            CandidateFact(
                field_path="receipt.transaction.total",
                value_type="money",
                value={"amount": 4.65, "currency": "USD"},
                currency="USD",
                evidence=[_evidence(context)],
                status="proposed",
            )
        ],
        line_item_candidates=[
            LineItemCandidateFact(
                line_item_type="receipt_item",
                ordinal=1,
                description="Coffee",
                net_amount=4.65,
                currency="USD",
                evidence=[_evidence(context)],
                status="proposed",
            )
        ],
        observation_candidates=[
            ObservationCandidateFact(
                observation_family="receipt",
                field_name="register_note",
                value_type="string",
                value="printed receipt",
                evidence=[_evidence(context)],
            )
        ],
    )

    assert admission.field_candidates[0].validation["candidateAdmissionFingerprint"] == (
        admission.events[0].candidate_fingerprint
    )
    assert admission.line_item_candidates[0].validation["candidateAdmissionFingerprint"] == (
        admission.events[1].candidate_fingerprint
    )
    assert admission.observation_candidates[0].metadata["candidateAdmissionFingerprint"] == (
        admission.events[2].candidate_fingerprint
    )


def test_missing_evidence_rejections_are_recorded_when_no_candidates_are_admitted() -> None:
    context = _context()

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[],
        observation_candidates=[],
        rejected_candidate_payloads=[
            {
                "candidate_kind": "field",
                "field_path": "receipt.transaction.total",
                "payload": {"value": {"amount": 4.65, "currency": "USD"}},
                "decision": "rejected_missing_evidence",
                "reasons": ["missing_concrete_evidence"],
                "evidence_concrete": False,
            }
        ],
    )

    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_missing_evidence": 1},
    }
    assert admission.events[0].field_path == "receipt.transaction.total"
    assert admission.events[0].payload_json["value"] == {"amount": 4.65, "currency": "USD"}


def test_payload_rejection_scan_records_candidates_dropped_before_admission() -> None:
    context = _context()

    rejected = rejected_candidates_from_payload(
        schema_name="receipt",
        payload={
            "line_items": [
                {
                    "description": "Identify and extract the schema",
                    "quantity": "1.0000",
                    "unit": "rows",
                    "amount": {"amount": 1.0, "currency": "USD"},
                    "evidence": [_evidence(context)],
                }
            ]
        },
        context=context,
        require_concrete_evidence=True,
    )

    assert rejected == [
        {
            "candidate_kind": "line_item",
            "field_path": None,
            "payload": {
                "description": "Identify and extract the schema",
                "quantity": "1.0000",
                "unit": "rows",
                "amount": {"amount": 1.0, "currency": "USD"},
                "evidence": [_evidence(context)],
            },
            "decision": "rejected_artifact",
            "reasons": ["prompt_or_schema_echo"],
            "evidence_concrete": True,
        }
    ]


def test_duplicate_candidates_are_rejected_before_insertion() -> None:
    context = _context()
    evidence = [_evidence(context)]
    first = LineItemCandidateFact(
        line_item_type="receipt_item",
        ordinal=1,
        description="Pellegrino Sparkler 16oz Bottle",
        gross_amount=5.0,
        net_amount=5.0,
        currency="USD",
        evidence=evidence,
        status="needs_review",
    )
    duplicate = LineItemCandidateFact(
        line_item_type="receipt_item",
        ordinal=2,
        description="  pellegrino sparkler 16oz bottle  ",
        gross_amount=5.0,
        net_amount=5.0,
        currency="USD",
        evidence=evidence,
        status="needs_review",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[first, duplicate],
        observation_candidates=[],
    )

    assert [candidate.description for candidate in admission.line_item_candidates] == [
        "Pellegrino Sparkler 16oz Bottle"
    ]
    assert [event.decision for event in admission.events] == [
        "admitted_review_required",
        "rejected_duplicate",
    ]


def test_admission_events_insert_with_lineage_and_version_fields() -> None:
    context = _context()
    extraction_id = uuid4()
    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[
            CandidateFact(
                field_path="receipt.merchant.display_name",
                value_type="string",
                value="Coffee Shop",
                evidence=[_evidence(context)],
                status="needs_review",
            )
        ],
        line_item_candidates=[],
        observation_candidates=[],
    )
    cursor = RecordingCursor()

    persist_candidate_admission_events(
        cursor,
        extraction_id=extraction_id,
        events=admission.events,
    )

    sql, params = cursor.queries[0]
    assert "INSERT INTO candidate_admission_events" in sql
    assert context.plan_id in params
    assert context.plan_task_id in params
    assert context.semantic_annotation_id in params
    assert context.region_envelope_version in params
    assert CANDIDATE_GATE_VERSION in params
    assert CONTRACT_REGISTRY_VERSION in params


def test_admission_event_payloads_are_json_serializable_with_candidate_dates() -> None:
    context = _context()
    extraction_id = uuid4()
    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[
            CandidateFact(
                field_path="receipt.transaction.date_local",
                value_type="date",
                value=date(2026, 5, 2),
                evidence=[_evidence(context)],
                status="needs_review",
            )
        ],
        line_item_candidates=[
            LineItemCandidateFact(
                line_item_type="service_line",
                ordinal=1,
                description="Scheduled service inspection",
                service_date=date(2026, 5, 2),
                net_amount=0.0,
                currency="USD",
                category_hint="service",
                evidence=[_evidence(context)],
                status="needs_review",
            )
        ],
        observation_candidates=[],
    )
    cursor = JsonSerializingCursor()

    persist_candidate_admission_events(
        cursor,
        extraction_id=extraction_id,
        events=admission.events,
    )

    assert [payload["value"] for payload in cursor.payloads if "value" in payload] == ["2026-05-02"]
    service_dates = [
        payload["service_date"] for payload in cursor.payloads if "service_date" in payload
    ]
    assert service_dates == ["2026-05-02"]


class RecordingCursor:
    def __init__(self) -> None:
        self.queries: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.queries.append((sql, params))


class JsonSerializingCursor(RecordingCursor):
    def __init__(self) -> None:
        super().__init__()
        self.payloads: list[dict[str, object]] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        super().execute(sql, params)
        jsonb_payload = cast(Any, params[-1])
        serialized = json.dumps(jsonb_payload.obj)
        self.payloads.append(json.loads(serialized))


def _context(*, canonical_target_schema: str = "receipt") -> CandidateAdmissionContext:
    return CandidateAdmissionContext(
        document_id=uuid4(),
        run_scope=ExtractionRunScope.semantic_region(
            semantic_annotation_id=uuid4(),
            source_semantic_region_id=uuid4(),
            semantic_type="receipt_payment_summary",
            granite_task="kvp",
            plan_id=uuid4(),
            plan_task_id=uuid4(),
            canonical_target_schema=canonical_target_schema,
            compatibility_mode="exact",
            contract_resolution_reason="exact_contract",
            region_envelope_version="phase8_5-region-envelope-v1",
        ),
        source_engine="granite_vision_3b",
        model_output_schema_name="granite_receipt_payment_summary.v1",
    )


def _evidence(context: CandidateAdmissionContext) -> dict[str, object]:
    return {
        "document_id": str(context.document_id),
        "semantic_annotation_id": str(context.semantic_annotation_id),
        "semantic_region_id": str(context.semantic_region_id),
        "page_number": 1,
        "source_engine": context.source_engine,
        "source_text": "Coffee Shop total $4.65",
    }
