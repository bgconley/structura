from __future__ import annotations

from uuid import uuid4

from lib.extraction.model_output_normalization import normalize_granite_region_output


def test_invoice_payment_summary_ignores_off_contract_alias_fields() -> None:
    document_id = uuid4()

    normalized, metadata = normalize_granite_region_output(
        document_id=document_id,
        schema_name="invoice",
        model_output_schema_name="granite_payment_summary.v1",
        payload={
            "payments": [],
            "invoice_number": "OFF-CONTRACT-INV",
            "totals": {"amount_paid": "$42.00"},
            "confidence": {"overall": 0.61},
        },
    )

    assert normalized["invoice"] == {}
    assert normalized["totals"] == {}
    assert metadata["rejected_fields"] == ["invoice_number", "totals"]
