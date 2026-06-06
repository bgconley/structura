from __future__ import annotations

import inspect
from dataclasses import fields
from datetime import UTC, datetime
from uuid import uuid4

from lib.extraction import reconciliation as reconciliation_module
from lib.extraction.reconciliation import (
    RegionExtraction,
    reconcile_invoice_region_extractions,
)
from lib.extraction.region_envelope import (
    EvidenceRef,
    RegionExtractionEnvelope,
    RegionFact,
    RegionLineItem,
)


def test_invoice_region_reconciliation_has_no_raw_payload_input() -> None:
    assert "normalized_json" not in {field.name for field in fields(RegionExtraction)}

    aggregate = reconcile_invoice_region_extractions(
        document_id=uuid4(),
        seller={"display_name": "MAX BMW", "party_type": "company"},
        created_at=datetime.now(UTC),
        regions=[
            RegionExtraction(
                extraction_id=uuid4(),
                semantic_region_id=uuid4(),
                semantic_type="invoice_line_item_table",
            ),
        ],
    )

    assert aggregate is None


def test_invoice_region_reconciliation_has_no_legacy_escape_hatches() -> None:
    signature = inspect.signature(reconcile_invoice_region_extractions)
    assert "allow_legacy_region_envelopes" not in signature.parameters
    assert "allow_legacy_raw_payloads" not in signature.parameters
    assert "document_fallback" not in signature.parameters

    source = inspect.getsource(reconciliation_module)
    assert "FORBIDDEN_CANONICAL_PLACEHOLDERS" not in source
    assert "semantic_type.endswith" not in source
    assert "legacy_invoice" not in source
    assert "resolve_claims_for_family" not in source
    assert "resolve_claim_regions_for_family" in source


def test_invoice_region_reconciliation_disables_envelope_fallback_by_default() -> None:
    document_id = uuid4()
    region_id = uuid4()
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        page_number=1,
        table_id="table-1",
        row_index=2,
        source_engine="granite_vision_3b",
    )

    aggregate = reconcile_invoice_region_extractions(
        document_id=document_id,
        seller={"display_name": "MAX BMW", "party_type": "company"},
        created_at=datetime.now(UTC),
        regions=[
            RegionExtraction(
                extraction_id=uuid4(),
                semantic_region_id=region_id,
                semantic_type="invoice_line_item_table",
                region_envelope=RegionExtractionEnvelope(
                    document_id=str(document_id),
                    semantic_region_id=str(region_id),
                    resolved_document_type="invoice",
                    semantic_type="invoice_line_item_table",
                    target_schema="invoice",
                    model_output_schema_name="granite_invoice_line_items.v1",
                    facts=[
                        RegionFact(
                            name="invoice.total_amount",
                            value={"amount": 42.0, "currency": "USD"},
                            value_type="money",
                            evidence=[evidence],
                        )
                    ],
                    line_items=[
                        RegionLineItem(
                            description="Envelope-only service",
                            net_amount=42.0,
                            currency_code="USD",
                            evidence=[evidence],
                            table_id="table-1",
                            row_index=2,
                            page_number=1,
                        )
                    ],
                ),
            )
        ],
    )

    assert aggregate is None
