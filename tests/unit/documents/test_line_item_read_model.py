from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import jsonschema
import pytest
import yaml
from pydantic import ValidationError

from lib.contracts.document_line_items import CanonicalLineItemRead
from lib.documents.line_item_read_model import canonical_line_item_payload


def line_item_row(**overrides):
    row = dict(
        id=uuid4(),
        document_id=uuid4(),
        line_item_type="service_line",
        ordinal=21,
        description="Recorded service",
        code="99213",
        code_system="CPT",
        service_date=date(2026, 1, 26),
        quantity=Decimal("1.2345"),
        unit="hour",
        unit_price=Decimal("0.0000"),
        gross_amount=Decimal("99999999999999.9999"),
        discount_amount=Decimal("-12.3400"),
        tax_amount=None,
        net_amount=Decimal("120.0100"),
        currency_code="EUR",
        source_kind="human",
        review_status="user_corrected",
        evidence_json=[
            {"pageNumber": 3, "sourceEngine": "human", "textSpan": {"start": 1, "end": 5}}
        ],
        validation_json={"warnings": ["Check source"]},
        accepted_at=datetime(2026, 9, 7, tzinfo=UTC),
        updated_at=datetime(2026, 9, 7, tzinfo=UTC),
    )
    return {**row, **overrides}


def test_rich_canonical_row_keeps_decimal_strings_nulls_and_evidence():
    payload = canonical_line_item_payload(line_item_row())
    assert payload["quantity"] == "1.2345"
    assert payload["unitPrice"] == "0.0000"
    assert payload["grossAmount"] == "99999999999999.9999"
    assert payload["discountAmount"] == "-12.3400"
    assert payload["netAmount"] == "120.0100"
    assert payload["taxAmount"] is None
    assert payload["serviceDate"] == "2026-01-26"
    assert payload["currency"] == "EUR"
    assert payload["sourceKind"] == "human" and payload["reviewStatus"] == "user_corrected"
    assert payload["evidence"][0]["pageNumber"] == 3
    assert payload["validation"] == {"warnings": ["Check source"]}
    assert payload["allowedAmount"] is None and payload["planPaidAmount"] is None
    jsonschema.validate(
        payload, CanonicalLineItemRead.model_json_schema(mode="serialization", by_alias=True)
    )
    schemas = yaml.safe_load(Path("contracts/api/openapi.yaml").read_text())["components"][
        "schemas"
    ]
    assert schemas["DocumentDetail"]["allOf"][1]["properties"]["lineItems"]["items"] == {
        "$ref": "#/components/schemas/CanonicalLineItemRead"
    }
    assert schemas["CanonicalLineItemRead"] == CanonicalLineItemRead.model_json_schema(
        mode="serialization", by_alias=True
    )
    jsonschema.validate(payload, schemas["CanonicalLineItemRead"])


def test_recorded_eob_allowed_and_plan_paid_keep_exact_decimals():
    payload = canonical_line_item_payload(
        line_item_row(
            allowed_amount=Decimal("99999999999999.9999"), plan_paid_amount=Decimal("0.0000")
        )
    )
    assert payload["allowedAmount"] == "99999999999999.9999"
    assert payload["planPaidAmount"] == "0.0000"


@pytest.mark.parametrize(
    "status", ["unreviewed", "needs_review", "rejected", "auto_accepted", "user_confirmed"]
)
def test_read_preserves_existing_status_without_promoting_or_calculating(status):
    payload = canonical_line_item_payload(
        line_item_row(review_status=status, net_amount=None, currency_code=None)
    )
    assert payload["reviewStatus"] == status
    assert payload["netAmount"] is None and payload["currency"] is None


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("0.00001")])
def test_invalid_decimal_is_not_silently_coerced(value):
    with pytest.raises(ValidationError):
        canonical_line_item_payload(line_item_row(net_amount=value))
