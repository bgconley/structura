import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from lib.document_parsing.page_understanding.claims import ProposedClaim
from lib.document_parsing.page_understanding.model import PageUnderstanding
from lib.document_parsing.page_understanding.registry import FIELD_RULES, RULE_BY_KEY
from lib.document_parsing.page_understanding.taxonomy import FAMILIES, TYPED_FAMILIES
from tests.fixtures.page_understanding_sources import locator, prose_page

CONTRACTS = Path(__file__).resolve().parents[4] / "contracts" / "schemas"


def _paths(schema, prefix=""):
    reference = schema.get("$ref", "")
    if reference.endswith("/partyCore"):
        return {
            prefix + "." + field
            for field in ("display_name", "normalized_name", "party_type", "identifiers", "address")
        }
    if reference or not schema.get("properties"):
        if schema.get("items", {}).get("properties"):
            return _paths(schema["items"], prefix + "[]")
        return {prefix}
    paths = set()
    for name, value in schema["properties"].items():
        if name in {
            "ordinal",
            "evidence",
            "schema_name",
            "schema_version",
            "document_id",
            "created_at",
            "metadata",
            "confidence",
            "validation",
        }:
            continue
        paths.update(_paths(value, f"{prefix}.{name}" if prefix else name))
    return paths


@pytest.mark.parametrize("family", ["receipt", "invoice", "medical_eob"])
def test_frozen_registry_covers_all_actual_schema_business_fields(family):
    expected = _paths(json.loads((CONTRACTS / f"{family}.v1.schema.json").read_text()))
    declared = {r.source_path for r in FIELD_RULES if r.key.startswith(family + ".")}
    assert expected <= declared, sorted(expected - declared)


def test_all_23_existing_families_survive_without_legacy_routing_labels():
    schema = json.loads((CONTRACTS / "document_classification.v1.schema.json").read_text())
    assert tuple(schema["properties"]["family"]["enum"]) == FAMILIES
    assert len(FAMILIES) == 23
    for family in FAMILIES:
        parsed = PageUnderstanding.model_validate(
            prose_page(family, unsupported=family not in TYPED_FAMILIES)
        )
        assert parsed.classification.primary_family == family
        assert parsed.elements[0].text == "A complete paragraph of retained reference wording."
        assert "route_profile" not in parsed.classification.model_dump()


def test_app_spec_fields_absent_from_old_registry_are_explicit_obligations():
    expected = {
        "receipt.merchant.address": "text",
        "receipt.transaction.time_local": "time",
        "receipt.transaction.payment_method": "text",
        "receipt.line_item.quantity": "quantity",
        "receipt.line_item.unit": "text",
        "receipt.line_item.unit_price": "money",
        "invoice.seller.display_name": "party",
        "invoice.buyer.display_name": "party",
        "invoice.purchase_order_number": "identifier",
        "invoice.remittance.instructions": "text",
        "invoice.remittance.address": "text",
        "invoice.due_date": "date",
        "medical_eob.processed_on": "date",
        "medical_eob.line_item.modifiers": "identifiers",
        "medical_eob.line_item.gross_amount": "money",
        "medical_eob.line_item.allowed_amount": "money",
        "medical_eob.line_item.plan_paid": "money",
        "medical_eob.line_item.amount": "money",
        "medical_eob.line_item.deductible": "money",
        "medical_eob.line_item.coinsurance": "money",
        "medical_eob.line_item.copay": "money",
    }
    assert {key: RULE_BY_KEY[key].value_type for key in expected} == expected
    assert RULE_BY_KEY["receipt.merchant.address"].obligation == "where_present"
    assert RULE_BY_KEY["invoice.purchase_order_number"].obligation == "where_present"
    assert RULE_BY_KEY["medical_eob.line_item.deductible"].obligation == "where_present"
    assert RULE_BY_KEY["medical_eob.line_item.amount"].source_path.endswith(
        "patient_responsibility"
    )
    assert RULE_BY_KEY["medical_eob.line_item.plan_paid"].source_path.endswith("plan_paid")


def test_eob_modifiers_preserve_order_and_digits_without_numeric_coercion():
    claim = {
        "canonical_key": "medical_eob.line_item.modifiers",
        "value_type": "identifiers",
        "typed_value": ["025", "59"],
        "raw_value": "025, 59",
        "primary_source": locator(0, "025, 59"),
        "supporting_sources": [],
        "physical_row": {"kind": "table_row", "element_index": 0, "row": 1},
        "uncalibrated_score": None,
    }
    assert TypeAdapter(ProposedClaim).validate_python(claim).typed_value == ("025", "59")
    claim["typed_value"] = ["25", "59"]
    with pytest.raises(ValidationError):
        TypeAdapter(ProposedClaim).validate_python(claim)


def test_registry_is_immutable_and_unknown_keys_or_party_types_fail():
    with pytest.raises(TypeError):
        RULE_BY_KEY["invoice.invented"] = FIELD_RULES[0]
    claim = {
        "canonical_key": "invoice.seller.party_type",
        "value_type": "enum",
        "typed_value": "alien",
        "raw_value": "Acme",
        "primary_source": locator(0, "Acme"),
        "supporting_sources": [],
        "physical_row": None,
        "uncalibrated_score": None,
    }
    with pytest.raises(ValidationError):
        TypeAdapter(ProposedClaim).validate_python(claim)
