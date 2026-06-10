from __future__ import annotations

from uuid import uuid4

from lib.extraction.evidence import has_concrete_evidence
from lib.extraction.evidence_context import EvidenceContext
from lib.extraction.model_output_line_items import service_record_line_item


def test_model_output_line_item_helper_parses_service_record_values_with_evidence() -> None:
    document_id = uuid4()
    region_id = uuid4()
    table_id = uuid4()

    item = service_record_line_item(
        ordinal=2,
        description="MOUNT AND BALANCE FRONT AND REAR TIRES.",
        category_hint="service",
        quantity="2",
        unit="EA",
        unit_price="$182.99",
        amount="$365.98",
        source_text="MOUNT AND BALANCE FRONT AND REAR TIRES. | labor_operation: TIRE-SVC",
        evidence_context=EvidenceContext(
            source_engine="granite_vision_3b",
            document_id=document_id,
            semantic_region_id=region_id,
            table_id=table_id,
            page_number=4,
        ),
    )

    assert item["ordinal"] == 2
    assert item["quantity"] == 2.0
    assert item["unit"] == "EA"
    assert item["unit_price"] == {"amount": 182.99}
    assert item["amount"] == {"amount": 365.98}
    assert has_concrete_evidence(item["evidence"]) is True
