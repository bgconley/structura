from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from lib.extraction.models import (
    ExtractionSourceDocument,
    GatewayExtraction,
    ModelRoute,
    ParsedPageText,
    PersistedExtraction,
)
from lib.extraction.region_envelope import EvidenceRef, RegionExtractionEnvelope, RegionFact
from lib.extraction.region_envelope_validation import claim_evidence_validation_payload
from lib.extraction.service import ExtractionService
from lib.semantic_annotations.models import SemanticExtractionTask, SemanticGroundingRef


def test_claim_evidence_validation_payload_ignores_normalized_projection() -> None:
    document_id = uuid4()
    region_id = uuid4()
    envelope = _envelope_with_claim_evidence(
        document_id=document_id,
        annotation_id=uuid4(),
        region_id=region_id,
        page_id=uuid4(),
    )

    payload = claim_evidence_validation_payload(envelope)

    assert "coverage" not in payload
    assert payload["claims"][0]["canonical_key"] == "receipt.transaction.total"
    assert payload["claims"][0]["evidence"][0]["semantic_region_id"] == str(region_id)


def test_extraction_service_validates_semantic_region_evidence_from_claims() -> None:
    document_id = uuid4()
    household_id = uuid4()
    annotation_id = uuid4()
    region_id = uuid4()
    source = _source(document_id=document_id, household_id=household_id)
    task = _task(
        document_id=document_id,
        annotation_id=annotation_id,
        region_id=region_id,
        page_id=source.pages[0].page_id,
    )
    captured: dict[str, Any] = {}

    def persist(*_args: object, **kwargs: object) -> PersistedExtraction:
        captured.update(kwargs)
        return _persisted()

    ExtractionService(
        gateway=ProjectionWithoutEvidenceGateway(
            document_id=document_id,
            annotation_id=annotation_id,
            region_id=region_id,
            page_id=source.pages[0].page_id,
        ),
        source_loader=lambda loaded_document_id: source,
        semantic_task_loader=lambda loaded_region_id: task,
        persister=persist,
    ).extract_document(
        document_id,
        schema_name="receipt",
        route_profile="docling_plus_granite_structured",
        semantic_region_id=region_id,
    )

    evidence_check = next(
        check
        for check in captured["validation"].checks
        if check["code"] == "evidence.concrete_locator"
    )
    assert evidence_check["status"] == "passed"
    assert captured["field_candidates"][0].value == {"amount": 4.65, "currency": "USD"}


class ProjectionWithoutEvidenceGateway:
    def __init__(
        self,
        *,
        document_id: UUID,
        annotation_id: UUID,
        region_id: UUID,
        page_id: UUID,
    ) -> None:
        self.document_id = document_id
        self.annotation_id = annotation_id
        self.region_id = region_id
        self.page_id = page_id

    def extract(
        self,
        source: ExtractionSourceDocument,
        *,
        schema_name: str,
        route_profile: str,
        semantic_task: SemanticExtractionTask | None = None,
    ) -> GatewayExtraction:
        del source, semantic_task
        envelope = _envelope_with_claim_evidence(
            document_id=self.document_id,
            annotation_id=self.annotation_id,
            region_id=self.region_id,
            page_id=self.page_id,
        )
        return GatewayExtraction(
            schema_name=schema_name,
            schema_version="v1",
            route=ModelRoute(
                source_engine="granite_vision_3b",
                model_name="granite",
                model_version="v1",
                prompt_version="phase8_5-granite-structured-v1",
                route_profile=route_profile,
            ),
            normalized_json={
                "schema_name": "receipt",
                "schema_version": "v1",
                "document_id": str(self.document_id),
                "transaction": {"total": {"amount": 999.99, "currency": "USD"}},
                "confidence": {"overall": 0.81},
            },
            raw_output_json={"modelInvoked": True},
            normalization_json={
                "regionEnvelope": envelope.model_dump(mode="json", exclude_none=True)
            },
        )


def _envelope_with_claim_evidence(
    *,
    document_id: UUID,
    annotation_id: UUID,
    region_id: UUID,
    page_id: UUID,
) -> RegionExtractionEnvelope:
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_annotation_id=str(annotation_id),
        semantic_region_id=str(region_id),
        page_id=str(page_id),
        page_number=1,
        source_engine="granite_vision_3b",
        source_text="$4.65",
        text_span={"start": 10, "end": 15, "basis": "page_text"},
        confidence=0.81,
    )
    return RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_annotation_id=str(annotation_id),
        semantic_region_id=str(region_id),
        resolved_document_type="receipt",
        semantic_type="receipt_payment_summary",
        target_schema="receipt",
        model_output_schema_name="granite_receipt_payment_summary.v1",
        coverage={
            "schema_name": "receipt",
            "schema_version": "v1",
            "confidence": {"overall": 0.81},
            "normalized_projection": {
                "schema_name": "receipt",
                "schema_version": "v1",
                "document_id": str(document_id),
                "transaction": {"total": {"amount": 999.99, "currency": "USD"}},
                "confidence": {"overall": 0.81},
            },
        },
        facts=[
            RegionFact(
                name="receipt.transaction.total",
                value={"amount": 4.65, "currency": "USD"},
                value_type="money",
                confidence=0.81,
                evidence=[evidence],
            )
        ],
    )


def _task(
    *,
    document_id: UUID,
    annotation_id: UUID,
    region_id: UUID,
    page_id: UUID,
) -> SemanticExtractionTask:
    return SemanticExtractionTask(
        region_id=region_id,
        annotation_id=annotation_id,
        document_id=document_id,
        semantic_type="receipt_payment_summary",
        granite_task="kvp",
        target_schema="receipt",
        expected_fields=("total_amount",),
        grounding=SemanticGroundingRef(kind="page", page_id=page_id),
    )


def _source(
    *,
    document_id: UUID,
    household_id: UUID,
) -> ExtractionSourceDocument:
    return ExtractionSourceDocument(
        document_id=document_id,
        household_id=household_id,
        title="Receipt",
        original_filename="receipt.pdf",
        mime_type="application/pdf",
        family="receipt",
        subtype=None,
        sensitivity="standard",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[ParsedPageText(page_id=uuid4(), page_number=1, text="Receipt $4.65 total")],
        elements=[],
        tables=[],
    )


def _persisted() -> PersistedExtraction:
    return PersistedExtraction(
        extraction_id=uuid4(),
        review_status="needs_review",
        candidate_count=0,
        canonical_count=0,
        review_task_count=0,
    )
