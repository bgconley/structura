from __future__ import annotations

from uuid import uuid4

from lib.extraction.extraction_repository import (
    _status_for_persisted_extraction,
    _supersede_current_extractions,
)
from lib.extraction.models import ValidationReport
from lib.extraction.normalization import line_item_candidates_from_extraction


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


def test_bmw_style_flat_granite_invoice_fields_create_line_item_candidates() -> None:
    validation = ValidationReport(
        needs_review=True,
        checks=[
            {
                "code": "json_schema",
                "status": "failed",
                "message": "Granite returned a noncanonical but useful flat payload.",
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

    assert [candidate.description for candidate in candidates] == [
        "PERFORM 600 MILE RUNNING-IN CHECK ACCORDING TO BMW CHECKLIST.",
        "MOUNT AND BALANCE FRONT AND REAR TIRES. DISPOSE OF OLD TIRES.",
        ":Gypoid axle oil G3",
        ":TIRE PR 4SC 160/60R15 67H",
        ":TIRE PR 4SC 120/70R15 56H",
    ]
    assert all(candidate.status == "needs_review" for candidate in candidates)
    assert candidates[0].net_amount == 250.00
    assert candidates[2].net_amount == 51.00


def test_bmw_wrapped_granite_invoice_lines_create_line_item_candidates() -> None:
    validation = ValidationReport(
        needs_review=True,
        checks=[
            {
                "code": "json_schema",
                "status": "failed",
                "message": "Granite returned useful rows under data.invoice_line_items.",
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

    assert [candidate.description for candidate in candidates] == [
        "PERFORM 600 MILE RUNNING-IN CHECK.",
        "removed rear wheel mounted and balanced rear tire",
    ]
    assert candidates[0].net_amount == 51.00
    assert candidates[1].net_amount == 465.66
    assert candidates[1].service_date.isoformat() == "2023-04-25"


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


class RecordingCursor:
    def __init__(self) -> None:
        self.queries: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.queries.append((sql, params))
