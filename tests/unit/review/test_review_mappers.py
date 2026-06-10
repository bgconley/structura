from __future__ import annotations

from uuid import uuid4

from lib.review.mappers import (
    evidence_refs_from_json,
    line_item_candidate_from_row,
    observation_candidate_from_row,
    review_task_from_row,
)


def test_review_task_mapper_exposes_candidate_reference_metadata() -> None:
    observation_id = uuid4()
    task = review_task_from_row(
        {
            "id": uuid4(),
            "document_id": uuid4(),
            "task_type": "observation_review",
            "status": "open",
            "priority": 65,
            "reason": "service_record.invoice_no requires review.",
            "metadata_json": {
                "fieldPath": "observations.service_record.invoice_no",
                "observationId": str(observation_id),
                "observationFamily": "service_record",
                "fieldName": "invoice_no",
            },
        }
    )

    assert task.field_path == "observations.service_record.invoice_no"
    assert task.metadata is not None
    assert task.metadata["observationId"] == str(observation_id)
    assert task.metadata["observationFamily"] == "service_record"


def test_observation_candidate_mapper_projects_contract_evidence() -> None:
    row = {
        "id": uuid4(),
        "document_id": uuid4(),
        "extraction_id": uuid4(),
        "observation_family": "service_record",
        "field_name": "invoice_no",
        "value_type": "string",
        "value_json": "6046058/1",
        "confidence": 0.83,
        "source_engine": "granite_vision_3b",
        "semantic_type": "generic_form_kvp",
        "model_output_schema_name": "granite_generic_kvp.v1",
        "evidence_json": [
            {
                "document_id": str(uuid4()),
                "semantic_annotation_id": str(uuid4()),
                "semantic_region_id": str(uuid4()),
                "page_id": str(uuid4()),
                "page_number": 2,
                "source_engine": "granite_vision_3b",
                "source_text": "Invoice No: 6046058/1",
                "text_span": {"start": 0, "end": 21, "basis": "page_text"},
                "confidence": 0.83,
            }
        ],
        "validation_json": {"needs_review": True},
        "status": "needs_review",
    }

    candidate = observation_candidate_from_row(row)

    assert candidate.field_name == "invoice_no"
    assert candidate.value == "6046058/1"
    assert len(candidate.evidence) == 1
    ref = candidate.evidence[0]
    assert ref.page_number == 2
    assert ref.source_text == "Invoice No: 6046058/1"
    assert ref.text_span is not None and ref.text_span.start == 0


def test_line_item_candidate_mapper_converts_numeric_columns() -> None:
    from decimal import Decimal

    row = {
        "id": uuid4(),
        "document_id": uuid4(),
        "extraction_id": uuid4(),
        "line_item_type": "service_item",
        "ordinal": 2,
        "code": "00 50 011",
        "service_date": None,
        "description": "PERFORM 600 MILE RUNNING-IN CHECK",
        "quantity": Decimal("1.0000"),
        "unit": None,
        "unit_price": Decimal("250.0000"),
        "net_amount": Decimal("250.0000"),
        "currency_code": "USD",
        "category_hint": None,
        "confidence": Decimal("0.8000"),
        "source_engine": "granite_vision_3b",
        "evidence_json": [
            {
                "page_number": 1,
                "source_engine": "granite_vision_3b",
                "table_id": str(uuid4()),
                "row_index": 1,
                "source_text": "600 MILE CHECK 250.00",
            }
        ],
        "validation_json": {},
        "status": "needs_review",
    }

    candidate = line_item_candidate_from_row(row)

    assert candidate.line_item_type == "service_item"
    assert candidate.net_amount == 250.0
    assert candidate.quantity == 1.0
    assert candidate.evidence[0].row_index == 1


def test_evidence_sanitizer_drops_lineage_keys_and_pageless_refs() -> None:
    refs = evidence_refs_from_json(
        [
            {
                "page_number": 1,
                "source_engine": "granite",
                "source_text": "total 42.00",
                "semantic_region_id": str(uuid4()),
            },
            {"source_engine": "granite_vision_3b", "source_text": "no page locator"},
            "not-a-dict",
        ]
    )

    assert len(refs) == 1
    assert refs[0]["pageNumber"] == 1
    # Model alias engines are normalized to contract engines.
    assert refs[0]["sourceEngine"] == "granite_vision_3b"
    assert "semantic_region_id" not in refs[0]


def test_evidence_sanitizer_requires_a_concrete_locator() -> None:
    refs = evidence_refs_from_json(
        [{"page_number": 3, "source_engine": "docling", "confidence": 0.9}]
    )

    assert refs == []
