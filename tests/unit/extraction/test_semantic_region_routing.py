from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from lib.contracts.registry import ContractRegistry
from lib.extraction.models import (
    ExtractionSourceDocument,
    GatewayExtraction,
    ModelRoute,
    ParsedPageText,
    PersistedExtraction,
)
from lib.extraction.service import ExtractionService
from lib.semantic_annotations.models import SemanticExtractionTask, SemanticGroundingRef


def test_extraction_service_loads_semantic_region_task_for_gateway() -> None:
    document_id = uuid4()
    household_id = uuid4()
    region_id = uuid4()
    source = _source(document_id=document_id, household_id=household_id)
    task = SemanticExtractionTask(
        region_id=region_id,
        annotation_id=uuid4(),
        document_id=document_id,
        semantic_type="invoice_line_item_table",
        granite_task="tables_json",
        target_schema="invoice",
        expected_fields=("line_items", "total_amount"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
        reason="Qwen semantic pass identified the invoice table.",
        confidence=0.91,
    )
    gateway = RecordingGateway()

    ExtractionService(
        gateway=gateway,
        source_loader=lambda loaded_document_id: source,
        semantic_task_loader=lambda loaded_region_id: task,
        persister=lambda *args, **kwargs: _persisted(),
    ).extract_document(
        document_id,
        schema_name="invoice",
        route_profile="docling_plus_granite_structured",
        semantic_region_id=region_id,
        allow_8b_rescue=False,
    )

    assert gateway.semantic_task == task


def test_extraction_service_realizes_semantic_task_schema_to_requested_schema() -> None:
    document_id = uuid4()
    household_id = uuid4()
    region_id = uuid4()
    source = _source(document_id=document_id, household_id=household_id)
    task = SemanticExtractionTask(
        region_id=region_id,
        annotation_id=uuid4(),
        document_id=document_id,
        semantic_type="invoice_line_item_table",
        granite_task="tables_json",
        target_schema="medical_eob",
        expected_fields=("line_items", "total_amount"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
        reason="Qwen semantic pass identified an invoice table but mislabeled schema.",
        confidence=0.91,
    )
    gateway = RecordingGateway()

    ExtractionService(
        gateway=gateway,
        source_loader=lambda loaded_document_id: source,
        semantic_task_loader=lambda loaded_region_id: task,
        persister=lambda *args, **kwargs: _persisted(),
    ).extract_document(
        document_id,
        schema_name="invoice",
        route_profile="docling_plus_granite_structured",
        semantic_region_id=region_id,
        allow_8b_rescue=False,
    )

    assert gateway.semantic_task is not None
    assert gateway.semantic_task.target_schema == "invoice"
    assert gateway.semantic_task.metadata["original_target_schema"] == "medical_eob"
    assert gateway.semantic_task.metadata["target_schema_repaired"] is True


def test_extraction_service_passes_semantic_region_scope_to_persister() -> None:
    document_id = uuid4()
    household_id = uuid4()
    line_region_id = uuid4()
    payment_region_id = uuid4()
    source = _source(document_id=document_id, household_id=household_id)
    tasks = {
        line_region_id: SemanticExtractionTask(
            region_id=line_region_id,
            annotation_id=uuid4(),
            document_id=document_id,
            semantic_type="invoice_line_item_table",
            granite_task="tables_json",
            target_schema="invoice",
            expected_fields=("line_items", "total_amount"),
            grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
            reason="Qwen semantic pass identified the invoice table.",
            confidence=0.91,
        ),
        payment_region_id: SemanticExtractionTask(
            region_id=payment_region_id,
            annotation_id=uuid4(),
            document_id=document_id,
            semantic_type="payment_summary",
            granite_task="kvp",
            target_schema="invoice",
            expected_fields=("amount_paid", "payment_reference"),
            grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
            reason="Qwen semantic pass identified the payment summary.",
            confidence=0.88,
        ),
    }
    persisted_scopes: list[SemanticExtractionTask | None] = []

    def persist(*_args: object, semantic_task: SemanticExtractionTask | None, **_kwargs: object):
        persisted_scopes.append(semantic_task)
        return _persisted()

    service = ExtractionService(
        gateway=RecordingGateway(needs_review=True),
        source_loader=lambda loaded_document_id: source,
        semantic_task_loader=lambda loaded_region_id: tasks[loaded_region_id],
        persister=persist,
    )

    service.extract_document(
        document_id,
        schema_name="invoice",
        route_profile="docling_plus_granite_structured",
        semantic_region_id=line_region_id,
    )
    service.extract_document(
        document_id,
        schema_name="invoice",
        route_profile="docling_plus_granite_structured",
        semantic_region_id=payment_region_id,
    )

    assert [scope.region_id if scope else None for scope in persisted_scopes] == [
        line_region_id,
        payment_region_id,
    ]


def test_extraction_service_does_not_rescue_needs_review_without_user_permission() -> None:
    document_id = uuid4()
    household_id = uuid4()
    region_id = uuid4()
    source = _source(document_id=document_id, household_id=household_id)
    task = SemanticExtractionTask(
        region_id=region_id,
        annotation_id=uuid4(),
        document_id=document_id,
        semantic_type="invoice_line_item_table",
        granite_task="tables_json",
        target_schema="invoice",
        expected_fields=("line_items", "total_amount"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
    )
    jobs = RecordingJobs()

    ExtractionService(
        gateway=RecordingGateway(needs_review=True),
        source_loader=lambda loaded_document_id: source,
        semantic_task_loader=lambda loaded_region_id: task,
        persister=lambda *args, **kwargs: _persisted(),
        jobs=jobs,
    ).extract_document(
        document_id,
        schema_name="invoice",
        route_profile="docling_plus_granite_structured",
        semantic_region_id=region_id,
    )

    assert jobs.created == []


def test_extraction_service_does_not_queue_rescue_when_qwen8_disabled_even_with_permission() -> (
    None
):
    document_id = uuid4()
    household_id = uuid4()
    region_id = uuid4()
    source = _source(document_id=document_id, household_id=household_id)
    task = SemanticExtractionTask(
        region_id=region_id,
        annotation_id=uuid4(),
        document_id=document_id,
        semantic_type="invoice_line_item_table",
        granite_task="tables_json",
        target_schema="invoice",
        expected_fields=("line_items", "total_amount"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
    )
    jobs = RecordingJobs()
    user_id = uuid4()

    ExtractionService(
        gateway=RecordingGateway(needs_review=True),
        source_loader=lambda loaded_document_id: source,
        semantic_task_loader=lambda loaded_region_id: task,
        persister=lambda *args, **kwargs: _persisted(),
        jobs=jobs,
    ).extract_document(
        document_id,
        schema_name="invoice",
        route_profile="docling_plus_granite_structured",
        semantic_region_id=region_id,
        allow_8b_rescue=True,
        requested_by="user",
        requested_by_user_id=user_id,
        user_intent_reason="User allowed one 8B rescue.",
    )

    assert jobs.created == []


def test_extraction_service_queues_rescue_with_user_permission_when_qwen8_enabled() -> None:
    document_id = uuid4()
    household_id = uuid4()
    region_id = uuid4()
    source = _source(document_id=document_id, household_id=household_id)
    task = SemanticExtractionTask(
        region_id=region_id,
        annotation_id=uuid4(),
        document_id=document_id,
        semantic_type="invoice_line_item_table",
        granite_task="tables_json",
        target_schema="invoice",
        expected_fields=("line_items", "total_amount"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
    )
    jobs = RecordingJobs()
    user_id = uuid4()

    ExtractionService(
        gateway=RecordingGateway(needs_review=True),
        source_loader=lambda loaded_document_id: source,
        semantic_task_loader=lambda loaded_region_id: task,
        persister=lambda *args, **kwargs: _persisted(),
        jobs=jobs,
        qwen8_enabled=True,
    ).extract_document(
        document_id,
        schema_name="invoice",
        route_profile="docling_plus_granite_structured",
        semantic_region_id=region_id,
        allow_8b_rescue=True,
        requested_by="user",
        requested_by_user_id=user_id,
        user_intent_reason="User allowed one 8B rescue.",
    )

    assert jobs.created[0]["job_type"] == "semantic_annotate"
    assert jobs.created[0]["queue_name"] == "semantic-annotations"
    payload = jobs.created[0]["payload"]
    ContractRegistry.load("contracts").validate_event_instance(
        "semantic_annotate_document_job.v1.schema.json",
        payload,
    )
    assert payload["job_id"] == str(jobs.created[0]["job_id"])
    assert payload["quality_mode"] == "rescue"
    assert payload["semantic_quality_mode"] == "smart"
    assert payload["allow_8b_rescue"] is True
    assert payload["requested_by_user_id"] == str(user_id)
    assert payload["user_intent_reason"] == "User allowed one 8B rescue."
    assert payload["source_semantic_region_id"] == str(region_id)
    assert payload["metadata"]["failure_class"] == "unreconciled_totals"


def test_extraction_service_does_not_enqueue_rescue_if_persist_fails() -> None:
    document_id = uuid4()
    household_id = uuid4()
    region_id = uuid4()
    source = _source(document_id=document_id, household_id=household_id)
    task = SemanticExtractionTask(
        region_id=region_id,
        annotation_id=uuid4(),
        document_id=document_id,
        semantic_type="invoice_line_item_table",
        granite_task="tables_json",
        target_schema="invoice",
        expected_fields=("line_items", "total_amount"),
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
    )
    jobs = RecordingJobs()

    def fail_persist(*_args: object, **_kwargs: object) -> PersistedExtraction:
        raise RuntimeError("persist failed")

    with pytest.raises(RuntimeError, match="persist failed"):
        ExtractionService(
            gateway=RecordingGateway(needs_review=True),
            source_loader=lambda loaded_document_id: source,
            semantic_task_loader=lambda loaded_region_id: task,
            persister=fail_persist,
            jobs=jobs,
        ).extract_document(
            document_id,
            schema_name="invoice",
            route_profile="docling_plus_granite_structured",
            semantic_region_id=region_id,
        )

    assert jobs.created == []


class RecordingGateway:
    def __init__(self, *, needs_review: bool = False) -> None:
        self.semantic_task: SemanticExtractionTask | None = None
        self.needs_review = needs_review

    def extract(
        self,
        source: ExtractionSourceDocument,
        *,
        schema_name: str,
        route_profile: str,
        semantic_task: SemanticExtractionTask | None = None,
    ) -> GatewayExtraction:
        self.semantic_task = semantic_task
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
                "schema_name": "invoice",
                "schema_version": "v1",
                "document_id": str(source.document_id),
                "seller": {
                    "display_name": "Acme Services",
                    "party_type": "company",
                    "evidence": [_evidence()],
                },
                "invoice": {
                    "invoice_number": "INV-100",
                    "issued_on": "2026-01-10",
                    "evidence": [_evidence()],
                },
                "line_items": [],
                "totals": {
                    "subtotal": {"amount": 10.0, "currency": "USD"},
                    "tax_total": {"amount": 1.0, "currency": "USD"},
                    "total": {"amount": 99.0, "currency": "USD"},
                    "evidence": [_evidence()],
                },
                "confidence": {"overall": 0.8},
                "validation": {"needs_review": self.needs_review, "checks": []},
                "created_at": datetime.now(UTC).isoformat(),
                "metadata": {},
            },
            raw_output_json={"modelInvoked": True},
        )


class RecordingJobs:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    def create_job(self, **kwargs: object) -> CreatedJob:
        if "job_id" not in kwargs:
            kwargs["job_id"] = uuid4()
        self.created.append(kwargs)
        return CreatedJob(job_id=kwargs["job_id"])  # type: ignore[arg-type]


@dataclass(frozen=True)
class CreatedJob:
    job_id: UUID


def _evidence() -> dict[str, object]:
    return {
        "page_number": 1,
        "source_engine": "granite_vision_3b",
        "source_text": "Invoice total $99.00",
        "confidence": 0.8,
    }


def _source(
    *,
    document_id: UUID,
    household_id: UUID,
) -> ExtractionSourceDocument:
    return ExtractionSourceDocument(
        document_id=document_id,
        household_id=household_id,
        title="Invoice",
        original_filename="invoice.pdf",
        mime_type="application/pdf",
        family="invoice",
        subtype=None,
        sensitivity="standard",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[
            ParsedPageText(
                page_id=uuid4(),
                page_number=1,
                text="Invoice total $10.00",
                image_bytes=b"fake-image",
                image_mime_type="image/png",
                image_sha256="d" * 64,
            )
        ],
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
