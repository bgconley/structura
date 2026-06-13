from __future__ import annotations

from uuid import uuid4

from lib.extraction.models import PersistedExtraction
from lib.extraction.service import ExtractionService
from lib.semantic_annotations.extraction_plan_repository import PlannedExtractionTask


def test_document_orchestration_runs_selected_tasks_and_reconciles_unique_targets() -> None:
    document_id = uuid4()
    annotation_id = uuid4()
    plan_id = uuid4()
    invoice_region_id = uuid4()
    receipt_region_id = uuid4()
    invoice_task_id = uuid4()
    receipt_task_id = uuid4()
    tasks = (
        PlannedExtractionTask(
            plan_id=plan_id,
            plan_task_id=invoice_task_id,
            semantic_annotation_id=annotation_id,
            semantic_region_id=invoice_region_id,
            semantic_type="invoice_line_item_table",
            target_schema="invoice",
            canonical_target_schema="invoice",
            compatibility_mode="exact",
            contract_resolution_reason="exact_contract",
            region_envelope_version="phase8_5-region-envelope-v1",
        ),
        PlannedExtractionTask(
            plan_id=plan_id,
            plan_task_id=receipt_task_id,
            semantic_annotation_id=annotation_id,
            semantic_region_id=receipt_region_id,
            semantic_type="service_record_line_item_table",
            target_schema="receipt",
            canonical_target_schema="service_record",
            compatibility_mode="compatible_alias",
            contract_resolution_reason="receipt_compatible_alias",
            region_envelope_version="phase8_5-region-envelope-v1",
        ),
    )
    service = RecordingDocumentOrchestrationService(
        planned_task_loader=lambda **_kwargs: list(tasks),
    )

    result = service.extract_semantic_annotation_document(
        document_id,
        semantic_annotation_id=annotation_id,
        plan_id=plan_id,
        requested_by="agent",
        run_id="uat-holdout-1",
    )

    assert [call["semantic_region_id"] for call in service.extract_calls] == [
        invoice_region_id,
        receipt_region_id,
    ]
    assert [call["plan_task_id"] for call in service.extract_calls] == [
        invoice_task_id,
        receipt_task_id,
    ]
    assert service.extract_calls[1]["canonical_target_schema"] == "service_record"
    assert service.reconcile_calls == [
        ("invoice", "invoice"),
        ("receipt", "service_record"),
    ]
    assert result.region_extraction_ids == (
        service.region_results[0].extraction_id,
        service.region_results[1].extraction_id,
    )
    assert result.aggregate_extraction_ids == tuple(
        aggregate.extraction_id for aggregate in service.aggregate_results
    )


class RecordingDocumentOrchestrationService(ExtractionService):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.extract_calls = []
        self.reconcile_calls = []
        self.region_results = [
            PersistedExtraction(uuid4(), "needs_review", 1, 0, 1),
            PersistedExtraction(uuid4(), "needs_review", 1, 0, 1),
        ]
        self.aggregate_results = [
            PersistedExtraction(uuid4(), "needs_review", 2, 0, 2),
            PersistedExtraction(uuid4(), "needs_review", 2, 0, 2),
        ]

    def extract_document(self, document_id, **kwargs):  # noqa: ANN001, ANN003
        del document_id
        self.extract_calls.append(kwargs)
        return self.region_results[len(self.extract_calls) - 1]

    def reconcile_semantic_annotation(self, **kwargs):  # noqa: ANN003
        self.reconcile_calls.append(
            (
                kwargs["schema_name"],
                kwargs.get("canonical_target_schema"),
            )
        )
        return self.aggregate_results[len(self.reconcile_calls) - 1]
