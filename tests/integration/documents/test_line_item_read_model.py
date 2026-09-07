from decimal import Decimal
from pathlib import Path

import jsonschema
import yaml
from psycopg.types.json import Jsonb

from tests.integration.documents.browse_support import browse_rows, create_identity, login


def test_document_api_returns_every_persisted_line_item_without_precision_loss(browse_corpus):
    document_id = browse_corpus.document("Canonical service rows")
    for ordinal in range(1, 26):
        browse_rows(
            """INSERT INTO canonical_line_items
            (document_id,line_item_type,ordinal,description,code,code_system,service_date,
             quantity,unit,unit_price,gross_amount,discount_amount,tax_amount,net_amount,
             currency_code,source_kind,review_status,evidence_json,validation_json)
            VALUES (%s,'service',%s,%s,'99213','CPT','2026-01-26',1.2345,'hour',0,
              99999999999999.9999,-12.34,NULL,%s,'EUR','human',%s,%s,%s)""",
            (
                document_id,
                ordinal,
                f"Canonical service {ordinal}",
                Decimal("120.0100"),
                "rejected" if ordinal == 25 else "user_confirmed",
                Jsonb(
                    [{"pageNumber": 3, "sourceEngine": "human", "textSpan": {"start": 1, "end": 5}}]
                ),
                Jsonb({"warnings": ["Retained validation"]}),
            ),
        )
    response = browse_corpus.client.get(f"/api/v1/documents/{document_id}")
    assert response.status_code == 200, response.text
    rows = response.json()["lineItems"]
    schemas = yaml.safe_load(Path("contracts/api/openapi.yaml").read_text())["components"][
        "schemas"
    ]
    for row in rows:
        jsonschema.validate(row, schemas["CanonicalLineItemRead"])
    assert [row["ordinal"] for row in rows] == list(range(1, 26))
    assert {row["documentId"] for row in rows} == {str(document_id)}
    assert rows[-1]["reviewStatus"] == "rejected"
    assert rows[-1]["sourceKind"] == "human"
    assert rows[-1]["grossAmount"] == "99999999999999.9999"
    assert rows[-1]["discountAmount"] == "-12.3400"
    assert rows[-1]["quantity"] == "1.2345"
    assert rows[-1]["unitPrice"] == "0.0000"
    assert rows[-1]["netAmount"] == "120.0100"
    assert rows[-1]["taxAmount"] is None
    assert rows[-1]["codeSystem"] == "CPT" and rows[-1]["serviceDate"] == "2026-01-26"
    assert rows[-1]["evidence"][0]["pageNumber"] == 3
    assert rows[-1]["validation"] == {"warnings": ["Retained validation"]}
    assert "allowedAmount" not in rows[-1]
    other = login(create_identity("other-line-item-reader"))
    assert other.get(f"/api/v1/documents/{document_id}").status_code == 404
