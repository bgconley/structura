from decimal import Decimal
from uuid import uuid4

import pytest

from lib.review.mappers import canonical_field_from_row, canonical_value


@pytest.mark.parametrize("kind", ["money", "number"])
@pytest.mark.parametrize("value", ["99999999999999.9999", "-12345678901234.0001", "0.0000"])
def test_canonical_numeric_read_preserves_exact_persisted_decimal(kind, value):
    row = {
        "id": uuid4(),
        "document_id": uuid4(),
        "field_path": "invoice.total_amount",
        "ordinal": 1,
        "value_type": kind,
        "numeric_value": Decimal(value),
        "currency_code": "USD",
        "json_value": {"amount": 1.5, "currency": "EUR"},
        "source_kind": "human",
        "review_status": "user_corrected",
        "evidence_json": [{"pageNumber": 1, "sourceEngine": "human", "sourceText": value}],
    }
    expected = {"amount": value, "currency": "USD"} if kind == "money" else value
    assert canonical_value(row) == expected
    response = canonical_field_from_row(row).model_dump(mode="json", by_alias=True)
    assert response["value"] == expected
    assert response["valueType"] == kind


@pytest.mark.parametrize("value", [0, 2**53 + 1, 2**63 - 1, -(2**63)])
def test_canonical_integer_transport_preserves_full_signed_bigint(value):
    row = {
        "id": uuid4(),
        "document_id": uuid4(),
        "field_path": "document.reference_integer",
        "ordinal": 1,
        "value_type": "integer",
        "integer_value": value,
        "source_kind": "human",
        "review_status": "user_corrected",
        "evidence_json": [{"pageNumber": 1, "sourceEngine": "human", "sourceText": str(value)}],
    }
    response = canonical_field_from_row(row).model_dump(mode="json", by_alias=True)
    assert response["value"] == str(value)
    assert response["valueType"] == "integer"
