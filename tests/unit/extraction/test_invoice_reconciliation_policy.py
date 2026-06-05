from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from lib.extraction.reconciliation import (
    RegionExtraction,
    reconcile_invoice_region_extractions,
)


def test_invoice_region_reconciliation_disables_raw_payloads_by_default() -> None:
    aggregate = reconcile_invoice_region_extractions(
        document_id=uuid4(),
        seller={"display_name": "MAX BMW", "party_type": "company"},
        created_at=datetime.now(UTC),
        regions=[
            RegionExtraction(
                extraction_id=uuid4(),
                semantic_region_id=uuid4(),
                semantic_type="invoice_line_item_table",
                normalized_json={
                    "schema_name": "invoice",
                    "line_items": [
                        {
                            "description": "Raw fallback service",
                            "amount": {"amount": 42.0, "currency": "USD"},
                        }
                    ],
                    "totals": {"total": {"amount": 42.0, "currency": "USD"}},
                },
            ),
        ],
        document_fallback={"invoice_number": "RAW-INV"},
    )

    assert aggregate is None
