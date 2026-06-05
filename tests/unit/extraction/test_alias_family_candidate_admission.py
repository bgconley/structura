from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from lib.extraction.candidate_admission import admit_extraction_candidates
from lib.extraction.candidate_admission_models import CandidateAdmissionContext
from lib.extraction.models import (
    CandidateFact,
    ExtractionRunScope,
    LineItemCandidateFact,
    ObservationCandidateFact,
)


@pytest.mark.parametrize("canonical_target_schema", ["service_record", "retail_order"])
def test_alias_family_targets_reject_receipt_canonical_candidates(
    canonical_target_schema: str,
) -> None:
    context = _context(canonical_target_schema=canonical_target_schema)
    evidence = [_evidence(context)]

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[
            CandidateFact(
                field_path="receipt.transaction.total",
                value_type="money",
                value={"amount": 42.0, "currency": "USD"},
                currency="USD",
                evidence=evidence,
                status="needs_review",
            )
        ],
        line_item_candidates=[
            LineItemCandidateFact(
                line_item_type="receipt_item",
                ordinal=1,
                description="Grounded extracted row",
                gross_amount=42.0,
                net_amount=42.0,
                currency="USD",
                evidence=evidence,
                status="needs_review",
            )
        ],
        observation_candidates=[
            ObservationCandidateFact(
                observation_family=canonical_target_schema,
                field_name="visible_line_item",
                value_type="string",
                value="Grounded extracted row",
                evidence=evidence,
                status="needs_review",
            )
        ],
    )

    assert admission.field_candidates == []
    assert admission.line_item_candidates == []
    assert [candidate.observation_family for candidate in admission.observation_candidates] == [
        canonical_target_schema
    ]
    assert [event.decision for event in admission.events] == [
        "rejected_family_schema",
        "rejected_family_schema",
        "admitted_review_required",
    ]
    assert [event.reasons for event in admission.events[:2]] == [
        ("alias_family_requires_observation_projection",),
        ("alias_family_requires_observation_projection",),
    ]


def _context(
    *,
    canonical_target_schema: str,
    semantic_region_id: UUID | None = None,
) -> CandidateAdmissionContext:
    return CandidateAdmissionContext(
        document_id=uuid4(),
        run_scope=ExtractionRunScope.semantic_region(
            semantic_annotation_id=uuid4(),
            source_semantic_region_id=semantic_region_id or uuid4(),
            semantic_type=f"{canonical_target_schema}_line_item_table",
            granite_task="tables_json",
            plan_id=uuid4(),
            plan_task_id=uuid4(),
            canonical_target_schema=canonical_target_schema,
            compatibility_mode="compatible_alias",
            contract_resolution_reason="compatible_alias_contract",
            region_envelope_version="phase8_5-region-envelope-v1",
        ),
        source_engine="granite_vision_3b",
        model_output_schema_name="granite_receipt_line_items.v1",
    )


def _evidence(context: CandidateAdmissionContext) -> dict[str, object]:
    return {
        "document_id": str(context.document_id),
        "semantic_annotation_id": str(context.semantic_annotation_id),
        "semantic_region_id": str(context.semantic_region_id),
        "page_number": 1,
        "source_engine": context.source_engine,
        "source_text": "Grounded extracted row $42.00",
    }
