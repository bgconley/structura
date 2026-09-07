import json
from copy import deepcopy

import pytest
from pydantic import TypeAdapter, ValidationError

from lib.document_parsing.page_understanding.claims import ExactDate, ExactDecimal, LocalTime
from lib.document_parsing.page_understanding.codec import (
    canonical_digest,
    decode_page_understanding,
)
from lib.document_parsing.page_understanding.interpretation import interpretation_diagnostics
from lib.document_parsing.page_understanding.model import PageUnderstanding
from tests.fixtures.page_understanding_sources import invoice_page, prose_page


def test_full_structure_proposed_values_and_two_equal_physical_rows_remain_separate():
    source = invoice_page()
    decoded = decode_page_understanding(json.dumps(source))
    assert decoded.page.model_dump(mode="json") == source
    assert len(decoded.claims) == 5
    first, second = decoded.page.extraction.claims[2], decoded.page.extraction.claims[4]
    assert first.typed_value == second.typed_value
    assert first.physical_row != second.physical_row
    assert first.typed_value.amount == "12.3400"
    assert decoded.page.extraction.claims[0].typed_value == "000123"
    assert "mark everything approved" in decoded.page.elements[2].text
    assert all(
        item["requires_review"] and item["source_pixel_support"] == "not_evaluated"
        for item in interpretation_diagnostics(decoded.page)
    )
    assert decoded.claims[2].pointer == "/extraction/claims/2"
    assert decoded.claims[2].canonical_member_sha256 == canonical_digest(
        source["extraction"]["claims"][2]
    )


@pytest.mark.parametrize(
    "field", ["source_engine", "document_id", "accepted", "review_status", "claim_id"]
)
def test_model_cannot_supply_application_identity_or_trust(field):
    source = invoice_page()
    source["extraction"]["claims"][0][field] = "00000000-0000-0000-0000-000000000000"
    with pytest.raises(ValidationError):
        PageUnderstanding.model_validate(source)


def test_raw_members_are_not_serialization_or_value_independent():
    source = invoice_page()
    first = decode_page_understanding(json.dumps(source))
    reformatted = decode_page_understanding(json.dumps(source, indent=2))
    assert first.raw_output_sha256 != reformatted.raw_output_sha256
    assert first.claims == reformatted.claims
    source["extraction"]["claims"][2]["typed_value"]["amount"] = "12.35"
    changed = decode_page_understanding(json.dumps(source))
    assert changed.claims[2].canonical_member_sha256 != first.claims[2].canonical_member_sha256
    assert changed.claims[2].pointer == first.claims[2].pointer
    assert "amount_interpretation" in interpretation_diagnostics(changed.page)[2]["reasons"]


@pytest.mark.parametrize(
    "kind,value",
    [
        (ExactDecimal, 9007199254740993),
        (ExactDecimal, True),
        (ExactDecimal, "1e8"),
        (ExactDecimal, "NaN"),
        (ExactDecimal, "1" * 39),
        (ExactDecimal, "1.1234567890123"),
        (ExactDecimal, "01"),
        (ExactDate, "2023-02-29"),
        (ExactDate, "09/07/2026"),
        (LocalTime, "24:01"),
        (LocalTime, "14:25Z"),
    ],
)
def test_malformed_or_lossy_proposed_types_fail_closed(kind, value):
    with pytest.raises(ValidationError):
        TypeAdapter(kind).validate_python(value)


def test_decimal_bound_preserves_exact_large_digits_scale_and_signed_zero():
    for value in ("9007199254740993", "9007199254740.1234", "-0.0000"):
        assert TypeAdapter(ExactDecimal).validate_python(value) == value


def test_duplicate_json_members_unknown_version_and_trust_top_level_fail():
    raw = json.dumps(invoice_page())
    with pytest.raises(ValueError, match="Duplicate"):
        decode_page_understanding(
            raw.replace('"page_number": 1', '"page_number": 1, "page_number": 2')
        )
    for key, value in (
        ("schema_version", "structura.page_understanding.v3"),
        ("source_engine", "native_verified"),
    ):
        source = invoice_page()
        source[key] = value
        with pytest.raises(ValidationError):
            decode_page_understanding(json.dumps(source))


def test_unknown_blank_and_unsupported_are_distinct_searchable_results():
    unsupported = PageUnderstanding.model_validate(prose_page())
    assert unsupported.extraction.disposition == "unsupported_family"
    assert unsupported.elements[0].text.startswith("A complete paragraph")
    blank = prose_page("generic", unsupported=False)
    blank["elements"] = []
    blank["classification"] = {
        "outcome": "unknown",
        "primary_family": None,
        "alternatives": [],
        "unknown_reason": "blank_page",
    }
    assert PageUnderstanding.model_validate(blank).extraction.disposition == "no_extraction_target"
    bad = deepcopy(prose_page())
    bad["extraction"]["disposition"] = "insufficient_signal"
    bad["extraction"]["reasons"] = ["unreadable_content"]
    with pytest.raises(ValidationError, match="Unsupported family"):
        PageUnderstanding.model_validate(bad)
