from __future__ import annotations

from uuid import UUID, uuid4

from lib.extraction.candidate_admission_models import CandidateAdmissionContext
from lib.extraction.candidate_admission_payloads import rejected_candidates_from_payload
from lib.extraction.models import ExtractionRunScope


def test_payload_rejection_scan_records_docling_table_consistency_dropped_rows() -> None:
    context = _context()

    rejected = rejected_candidates_from_payload(
        schema_name="invoice",
        payload={
            "schema_name": "invoice",
            "line_items": [
                {
                    "description": "Grounded row",
                    "row_index": 1,
                    "amount": {"amount": 99.0, "currency": "USD"},
                    "evidence": [_evidence(context)],
                }
            ],
            "metadata": {
                "tableConsistency": {
                    "rejectedRows": [
                        {
                            "payload": {
                                "description": "Invented row",
                                "amount": "$12.00",
                            },
                            "reason": "candidate.missing_docling_row_index",
                        }
                    ]
                }
            },
        },
        context=context,
        require_concrete_evidence=True,
    )

    assert rejected == [
        {
            "candidate_kind": "line_item",
            "field_path": None,
            "payload": {"description": "Invented row", "amount": "$12.00"},
            "decision": "rejected_table_consistency",
            "reasons": ["candidate.missing_docling_row_index"],
            "evidence_concrete": False,
        }
    ]


def _context(
    *,
    semantic_region_id: UUID | None = None,
) -> CandidateAdmissionContext:
    return CandidateAdmissionContext(
        document_id=uuid4(),
        run_scope=ExtractionRunScope.semantic_region(
            semantic_annotation_id=uuid4(),
            source_semantic_region_id=semantic_region_id or uuid4(),
            semantic_type="invoice_line_item_table",
            granite_task="tables_json",
            plan_id=uuid4(),
            plan_task_id=uuid4(),
            canonical_target_schema="invoice",
            compatibility_mode="exact",
            contract_resolution_reason="exact_contract",
            region_envelope_version="phase8_5-region-envelope-v1",
        ),
        source_engine="granite_vision_3b",
        model_output_schema_name="granite_invoice_line_items.v1",
    )


def _evidence(context: CandidateAdmissionContext) -> dict[str, object]:
    return {
        "document_id": str(context.document_id),
        "semantic_annotation_id": str(context.semantic_annotation_id),
        "semantic_region_id": str(context.semantic_region_id),
        "page_number": 1,
        "source_engine": context.source_engine,
        "source_text": "Invoice service row $99.00",
    }
