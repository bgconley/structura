from __future__ import annotations

from pathlib import Path
from typing import cast
from uuid import uuid4

from lib.extraction import extraction_repository as extraction_repo
from lib.extraction.claims import Claim
from lib.extraction.extraction_repository import (
    _persist_extraction_rows,
    _quality_outcome_for_extraction,
    _review_status_for_extraction,
    _status_for_persisted_extraction,
    _supersede_current_extractions,
    _update_document_classification,
)
from lib.extraction.models import (
    ClassificationDecision,
    ExtractionRunScope,
    ExtractionSourceDocument,
    GatewayExtraction,
    ModelRoute,
    ValidationReport,
)
from lib.extraction.normalization import (
    field_candidates_from_extraction,
    line_item_candidates_from_extraction,
    observation_candidates_from_extraction,
)
from lib.extraction.region_envelope import EvidenceRef, RegionExtractionEnvelope, RegionFact
from lib.storage import StoredObject


def test_schema_validation_review_does_not_mark_persisted_extraction_failed() -> None:
    validation = ValidationReport(
        needs_review=True,
        checks=[
            {
                "code": "json_schema",
                "status": "failed",
                "message": "Model output did not match the target schema.",
            }
        ],
    )

    assert _status_for_persisted_extraction(validation) == "completed"


def test_model_backed_semantic_region_extraction_review_status_is_conservative() -> None:
    extraction = GatewayExtraction(
        schema_name="document_observation",
        schema_version="v1",
        route=ModelRoute(
            source_engine="granite_vision_3b",
            model_name="granite",
            model_version="v1",
            prompt_version="prompt",
            route_profile="route",
        ),
        normalized_json={},
        raw_output_json={},
    )
    validation = ValidationReport(needs_review=False, checks=[])

    status = _review_status_for_extraction(
        extraction=extraction,
        validation=validation,
        run_scope=ExtractionRunScope.semantic_region(
            semantic_annotation_id=uuid4(),
            source_semantic_region_id=uuid4(),
            semantic_type="generic_form_kvp",
            granite_task="kvp",
        ),
    )

    assert status == "needs_review"


def test_non_model_semantic_region_can_keep_auto_accepted_review_status() -> None:
    extraction = GatewayExtraction(
        schema_name="invoice",
        schema_version="v1",
        route=ModelRoute(
            source_engine="docling",
            model_name="docling-heuristic-extractor",
            model_version="phase4-v1",
            prompt_version="no-prompt-deterministic-v1",
            route_profile="docling_plus_granite_structured",
        ),
        normalized_json={},
        raw_output_json={},
    )
    validation = ValidationReport(needs_review=False, checks=[])

    status = _review_status_for_extraction(
        extraction=extraction,
        validation=validation,
        run_scope=ExtractionRunScope.semantic_region(
            semantic_annotation_id=uuid4(),
            source_semantic_region_id=uuid4(),
            semantic_type="billing_summary",
            granite_task="kvp",
        ),
    )

    assert status == "auto_accepted"


def test_quality_outcome_is_persisted_from_aggregate_payload_metadata() -> None:
    payload = {
        "schema_name": "invoice",
        "metadata": {
            "quality_outcome": "needs_human_review",
            "claim_resolution_decisions": [
                {
                    "canonical_key": "invoice.total_amount",
                    "decision": "needs_review",
                    "reason_code": "cross_field_arithmetic_conflict",
                }
            ],
        },
    }

    assert _quality_outcome_for_extraction(payload) == "needs_human_review"


def test_quality_outcome_stays_null_for_rows_without_resolver_outcome() -> None:
    assert _quality_outcome_for_extraction({}) is None
    assert _quality_outcome_for_extraction({"metadata": {}}) is None
    assert _quality_outcome_for_extraction({"metadata": []}) is None
    assert _quality_outcome_for_extraction({"metadata": {"quality_outcome": "made_up"}}) is None
    assert _quality_outcome_for_extraction({"metadata": {"quality_outcome": 42}}) is None


def test_every_resolver_quality_outcome_is_persistable() -> None:
    for outcome in (
        "extracted_cleanly",
        "needs_human_review",
        "insufficient_signal",
        "no_extraction_target",
        "pipeline_failed",
    ):
        payload = {"metadata": {"quality_outcome": outcome}}
        assert _quality_outcome_for_extraction(payload) == outcome


def test_flat_granite_invoice_fields_do_not_create_line_item_candidates() -> None:
    validation = ValidationReport(
        needs_review=True,
        checks=[
            {
                "code": "json_schema",
                "status": "failed",
                "message": "Granite returned off-contract flat fields.",
            }
        ],
    )
    payload = {
        "service_description": [
            "PERFORM 600 MILE RUNNING-IN CHECK ACCORDING TO BMW CHECKLIST.",
            "MOUNT AND BALANCE FRONT AND REAR TIRES. DISPOSE OF OLD TIRES.",
        ],
        "parts": [
            ":Gypoid axle oil G3",
            ":TIRE PR 4SC 160/60R15 67H",
            ":TIRE PR 4SC 120/70R15 56H",
        ],
        "labor_cost": ["250.00", "127.50"],
        "parts_cost": ["51.00", "182.99", "143.99"],
        "total_amount": ["795.55"],
        "confidence": {"overall": 0.73},
    }

    candidates = line_item_candidates_from_extraction(
        schema_name="invoice",
        payload=payload,
        validation=validation,
        source_engine="granite_vision_3b",
    )

    assert candidates == []


def test_wrapped_granite_invoice_lines_do_not_create_line_item_candidates() -> None:
    validation = ValidationReport(
        needs_review=True,
        checks=[
            {
                "code": "json_schema",
                "status": "failed",
                "message": "Granite returned off-contract rows under data.invoice_line_items.",
            }
        ],
    )
    payload = {
        "data": {
            "invoice_line_items": [
                {
                    "service_description": "PERFORM 600 MILE RUNNING-IN CHECK.",
                    "parts": "Gasket ring, Hypoid axle oil G3",
                    "labor": "3.72",
                    "subtotal": "51.00",
                    "total_due": "51.00",
                },
                {
                    "service_type": "removed rear wheel mounted and balanced rear tire",
                    "service_cost": "465.66",
                    "service_date": "04/25/23",
                    "service_provider": "MAX BMW Motorcycles",
                },
                {
                    "description": "Customer Information",
                    "category_hint": "Customer Information",
                },
                {
                    "description": "Transaction information",
                    "category_hint": "Transaction information",
                    "amount": "4",
                },
            ]
        },
        "confidence": {"overall": 0.73},
    }

    candidates = line_item_candidates_from_extraction(
        schema_name="invoice",
        payload=payload,
        validation=validation,
        source_engine="granite_vision_3b",
    )

    assert candidates == []


def test_prompt_echo_line_items_are_rejected_before_candidate_creation() -> None:
    validation = ValidationReport(needs_review=True, checks=[])
    payload = {
        "line_items": [
            {
                "description": "Identify and extract the schema of all the tables in the image",
                "quantity": "1.0000",
                "unit_price": {"amount": 1.0, "currency": "USD"},
                "amount": {"amount": 1.0, "currency": "USD"},
                "unit": "rows",
            },
            {
                "description": "Pellegrino Sparkler 16oz Bottle",
                "amount": {"amount": 5.0, "currency": "USD"},
            },
        ]
    }

    candidates = line_item_candidates_from_extraction(
        schema_name="receipt",
        payload=payload,
        validation=validation,
        source_engine="granite_vision_3b",
    )

    assert [candidate.description for candidate in candidates] == [
        "Pellegrino Sparkler 16oz Bottle"
    ]


def test_schema_echo_money_dict_line_items_are_rejected_before_candidate_creation() -> None:
    validation = ValidationReport(needs_review=True, checks=[])
    payload = {
        "line_items": [
            {
                "description": "Generated row",
                "category_hint": "schema",
                "quantity": "1.0000",
                "unit_price": {"amount": 1.0, "currency": "USD"},
                "amount": {"amount": 1.0, "currency": "USD"},
                "unit": "rows",
            },
            {
                "description": "Pellegrino Sparkler 16oz Bottle",
                "amount": {"amount": 5.0, "currency": "USD"},
            },
        ]
    }

    candidates = line_item_candidates_from_extraction(
        schema_name="receipt",
        payload=payload,
        validation=validation,
        source_engine="granite_vision_3b",
    )

    assert [candidate.description for candidate in candidates] == [
        "Pellegrino Sparkler 16oz Bottle"
    ]


def test_model_region_line_items_require_concrete_evidence_when_requested() -> None:
    validation = ValidationReport(needs_review=True, checks=[])
    evidence = [{"page_number": 1, "page_id": str(uuid4()), "semantic_region_id": str(uuid4())}]
    payload = {
        "line_items": [
            {
                "description": "Ungrounded Coffee",
                "amount": {"amount": 4.25, "currency": "USD"},
            },
            {
                "description": "Grounded Coffee",
                "amount": {"amount": 4.25, "currency": "USD"},
                "evidence": evidence,
            },
        ]
    }

    candidates = line_item_candidates_from_extraction(
        schema_name="receipt",
        payload=payload,
        validation=validation,
        source_engine="granite_vision_3b",
        require_concrete_evidence=True,
    )

    assert [candidate.description for candidate in candidates] == ["Grounded Coffee"]


def test_model_region_field_candidates_require_concrete_evidence_when_requested() -> None:
    validation = ValidationReport(needs_review=True, checks=[])
    evidence = [{"page_number": 1, "page_id": str(uuid4()), "semantic_region_id": str(uuid4())}]
    payload = {
        "merchant": {
            "display_name": "Coffee Shop",
            "evidence": evidence,
        },
        "transaction": {
            "date_local": "2026-04-30",
            "subtotal": {"amount": 4.25, "currency": "USD"},
            "tax": {"amount": 0.40, "currency": "USD", "evidence": evidence},
            "total": {"amount": 4.65, "currency": "USD"},
        },
    }

    candidates = field_candidates_from_extraction(
        document_id=uuid4(),
        schema_name="receipt",
        payload=payload,
        validation=validation,
        source_engine="granite_vision_3b",
        require_concrete_evidence=True,
    )

    assert [candidate.field_path for candidate in candidates] == [
        "receipt.merchant.display_name",
        "receipt.transaction.tax",
    ]


def test_placeholder_observations_are_rejected_before_candidate_creation() -> None:
    validation = ValidationReport(needs_review=True, checks=[])
    payload = {
        "observations": [
            {
                "field_name": "visible_field",
                "value": "visible value",
                "value_type": "string",
            },
            {
                "field_name": "appeal_deadline",
                "value": "2026-03-01",
                "value_type": "date",
                "evidence": [{"page_id": str(uuid4()), "semantic_region_id": str(uuid4())}],
            },
            {
                "field_name": "denial_reason",
                "value": "null",
                "value_type": "string",
            },
        ]
    }

    candidates = observation_candidates_from_extraction(
        schema_name="document_observation",
        payload=payload,
        validation=validation,
    )

    assert [(candidate.field_name, candidate.value) for candidate in candidates] == [
        ("appeal_deadline", "2026-03-01")
    ]


def test_model_region_observations_require_concrete_evidence_when_requested() -> None:
    validation = ValidationReport(needs_review=True, checks=[])
    evidence = [{"page_number": 1, "page_id": str(uuid4()), "semantic_region_id": str(uuid4())}]
    payload = {
        "observations": [
            {
                "field_name": "appeal_deadline",
                "value": "2026-03-01",
                "value_type": "date",
            },
            {
                "field_name": "denial_reason",
                "value": "Not medically necessary",
                "value_type": "string",
                "evidence": evidence,
            },
        ]
    }

    candidates = observation_candidates_from_extraction(
        schema_name="document_observation",
        payload=payload,
        validation=validation,
        require_concrete_evidence=True,
    )

    assert [(candidate.field_name, candidate.value) for candidate in candidates] == [
        ("denial_reason", "Not medically necessary")
    ]


def test_persist_extraction_rows_persists_claims_from_region_envelope(
    monkeypatch,
    tmp_path: Path,
) -> None:
    document_id = uuid4()
    extraction_id = uuid4()
    annotation_id = uuid4()
    region_id = uuid4()
    source = ExtractionSourceDocument(
        document_id=document_id,
        household_id=uuid4(),
        title="Invoice",
        original_filename="invoice.pdf",
        mime_type="application/pdf",
        family="invoice",
        subtype=None,
        sensitivity="normal",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[],
        elements=[],
        tables=[],
    )
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_annotation_id=str(annotation_id),
        semantic_region_id=str(region_id),
        resolved_document_type="invoice",
        semantic_type="payment_summary",
        target_schema="invoice",
        model_output_schema_name="docling_text_kvp.v1",
        facts=[
            RegionFact(
                name="invoice.invoice_number",
                value="INV-100",
                value_type="string",
                evidence=[
                    EvidenceRef(
                        document_id=str(document_id),
                        semantic_annotation_id=str(annotation_id),
                        semantic_region_id=str(region_id),
                        page_number=1,
                        element_id="invoice-number",
                        source_engine="docling",
                    )
                ],
            )
        ],
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(extraction_repo, "db_connection", lambda: _FakeConnection())
    monkeypatch.setattr(extraction_repo, "_lock_document", lambda *args, **kwargs: None)
    monkeypatch.setattr(extraction_repo, "_supersede_current_assets", lambda *args, **kwargs: None)
    monkeypatch.setattr(extraction_repo, "_insert_artifact_asset", lambda *args, **kwargs: uuid4())
    monkeypatch.setattr(
        extraction_repo,
        "_supersede_current_extractions",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        extraction_repo,
        "_insert_extraction_run_row",
        lambda *args, **kwargs: extraction_id,
    )
    monkeypatch.setattr(
        extraction_repo,
        "update_plan_task_visual_summary",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        extraction_repo,
        "persist_candidate_admission_events",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(extraction_repo, "promote_candidates", lambda *args, **kwargs: 0)
    monkeypatch.setattr(extraction_repo, "create_review_tasks", lambda *args, **kwargs: 0)
    monkeypatch.setattr(extraction_repo, "update_document_rollups", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        extraction_repo,
        "refresh_document_chunk_projection",
        lambda *args, **kwargs: None,
    )

    def capture_claims(cur, *, extraction_id, claims, run_scope):
        captured["cursor"] = cur
        captured["extraction_id"] = extraction_id
        captured["claims"] = list(claims)
        captured["run_scope"] = run_scope

    monkeypatch.setattr(extraction_repo, "persist_extraction_claims", capture_claims)

    _persist_extraction_rows(
        GatewayExtraction(
            schema_name="invoice",
            schema_version="v1",
            route=ModelRoute(
                source_engine="docling",
                model_name="docling-text",
                model_version="v1",
                prompt_version="none",
                route_profile="docling_text",
            ),
            normalized_json={"schema_name": "invoice"},
            raw_output_json={},
            model_output_schema_name="docling_text_kvp.v1",
            normalization_json={
                "regionEnvelope": envelope.model_dump(mode="json", exclude_none=True),
                "regionEnvelopeVersion": "phase8_5-region-envelope-v1",
            },
        ),
        source=source,
        validation=ValidationReport(needs_review=True, checks=[]),
        field_candidates=[],
        line_item_candidates=[],
        observation_candidates=[],
        run_scope=ExtractionRunScope.semantic_region(
            semantic_annotation_id=annotation_id,
            source_semantic_region_id=region_id,
            semantic_type="payment_summary",
            granite_task="kvp",
            region_envelope_version="phase8_5-region-envelope-v1",
        ),
        raw_object=_stored(tmp_path, "raw"),
        normalized_object=_stored(tmp_path, "normalized"),
    )

    claims = cast(list[Claim], captured["claims"])
    run_scope = cast(ExtractionRunScope, captured["run_scope"])
    assert captured["extraction_id"] == extraction_id
    assert len(claims) == 1
    assert claims[0].canonical_key == "invoice.invoice_number"
    assert claims[0].anchor.docling_element_ids == ("invoice-number",)
    assert run_scope.source_semantic_region_id == region_id


def test_supersede_current_extractions_is_scoped_to_semantic_region() -> None:
    cur = RecordingCursor()
    document_id = uuid4()
    region_id = uuid4()

    _supersede_current_extractions(
        cur,
        document_id,
        "invoice",
        extraction_scope="semantic_region",
        source_semantic_region_id=region_id,
    )

    sql, params = cur.queries[0]
    assert "extraction_scope = %s" in sql
    assert "source_semantic_region_id = %s" in sql
    assert params == (
        document_id,
        "invoice",
        "semantic_region",
        region_id,
    )


def test_phase4_classification_update_preserves_authoritative_semantic_family() -> None:
    cur = RecordingCursor()
    source = ExtractionSourceDocument(
        document_id=uuid4(),
        household_id=uuid4(),
        title="Phenix Title Seller Info",
        original_filename="phenix.pdf",
        mime_type="application/pdf",
        family="real_estate_title",
        subtype=None,
        sensitivity="normal",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[],
        elements=[],
        tables=[],
    )
    decision = ClassificationDecision(
        payload={
            "family": "receipt",
            "subtype": None,
            "confidence": {"overall": 0.8},
        },
        needs_review=False,
    )

    _update_document_classification(cur, decision, source, "auto_accepted")

    sql, _params = cur.queries[0]
    assert "metadata_json #> '{phase8_5,semantic_classification}' IS NOT NULL" in sql
    assert "document_family ELSE %s::document_family_enum" in sql
    assert "family_confidence ELSE %s" in sql


class RecordingCursor:
    def __init__(self) -> None:
        self.queries: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.queries.append((sql, params))


def _stored(tmp_path: Path, name: str) -> StoredObject:
    path = tmp_path / f"{name}.json"
    path.write_text("{}", encoding="utf-8")
    return StoredObject(
        uri=f"objects://test/{name}.json",
        sha256="0" * 64,
        byte_size=2,
        path=path,
        created=False,
    )


class _FakeConnection:
    def __init__(self) -> None:
        self.cursor_obj = _FakeCursor()
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True


class _FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False
