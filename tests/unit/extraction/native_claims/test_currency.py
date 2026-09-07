from dataclasses import replace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from lib.extraction.native_claims.errors import NativeClaimError
from lib.extraction.native_claims.models import (
    NativeClaim,
    NativeClaimConfiguration,
    NativePageRequest,
)
from lib.extraction.native_claims.normalization import normalize_page_claims
from lib.extraction.native_claims.projection import diagnostic_projection
from lib.extraction.native_claims.values import NativeMoney, type_recorded_text
from tests.fixtures.native_claim_source import pure_source


def request_for(source, *, key="invoice.line_item.amount", table=False):
    page = source.structure.pages[0]
    locations = []
    if table:
        table_row = page.tables[0]
        locations = [
            {
                "element_id": table_row.element_id,
                "table_id": table_row.id,
                "cell_id": cell.id,
                "text_start": 0,
                "text_end": len(cell.text),
            }
            for cell in table_row.cells
        ]
    else:
        locations = [
            {"element_id": e.id, "text_start": 0, "text_end": len(e.text)} for e in page.elements
        ]
    return NativePageRequest(
        page_number=1,
        disposition="complete",
        claims=tuple(
            {"canonical_key": key, "value_type": "money", "anchor": loc} for loc in locations
        ),
    )


@pytest.mark.parametrize("table", [False, True])
def test_identical_values_keep_physical_rows_and_exact_currency(table):
    binding, source = pure_source(table=table)
    request = request_for(source, table=table)
    claims = normalize_page_claims(binding, NativeClaimConfiguration(), source, request)
    assert len({c.claim_id for c in claims}) == len({c.group_id for c in claims}) == 2
    assert all(
        c.typed_value == NativeMoney(amount="9007199254740.1234", currency="USD") for c in claims
    )
    assert normalize_page_claims(binding, NativeClaimConfiguration(), source, request) == claims
    projection = diagnostic_projection(claims)
    assert len(projection["line_rows"]) == 2
    assert projection["claims_are_accepted_facts"] is False
    assert projection["source_pixel_support"] == "not_evaluated"
    assert all(c.derivation == "structure_normalization" and c.requires_review for c in claims)


def test_logical_identity_excludes_value_but_payload_hash_records_change():
    binding, source = pure_source(texts=("USD 1.0000",))
    request = request_for(source)
    first = normalize_page_claims(binding, NativeClaimConfiguration(), source, request)[0]
    page = source.structure.pages[0]
    changed = page.model_copy(
        update={"elements": (page.elements[0].model_copy(update={"text": "USD 2.0000"}),)}
    )
    other = replace(source, structure=source.structure.model_copy(update={"pages": (changed,)}))
    second = normalize_page_claims(binding, NativeClaimConfiguration(), other, request)[0]
    assert first.claim_id == second.claim_id
    assert first.fingerprint != second.fingerprint


@pytest.mark.parametrize(
    "kind,value,expected",
    [
        ("number", "9007199254740993", "9007199254740993"),
        ("quantity", "-12.3400", "-12.3400"),
        ("identifier", "000123", "000123"),
        ("date", "2024-02-29", "2024-02-29"),
        ("boolean", "false", False),
        ("money", "42.1500", NativeMoney(amount="42.1500", currency=None)),
    ],
)
def test_exact_typing(kind, value, expected):
    assert type_recorded_text(kind, value) == expected


@pytest.mark.parametrize(
    "kind,value",
    [
        ("money", "$42.15"),
        ("money", "USD 1,000.00"),
        ("number", "NaN"),
        ("number", "Infinity"),
        ("number", "1e30"),
        ("number", "01"),
        ("number", "1" * 39),
        ("date", "2023-02-29"),
        ("date", "9/7/2026"),
        ("boolean", "yes"),
    ],
)
def test_ambiguous_or_unbounded_typing_fails_without_guessing(kind, value):
    with pytest.raises(NativeClaimError):
        type_recorded_text(kind, value)


def test_native_emission_and_supplied_typed_values_fail_closed():
    binding, source = pure_source()
    payload = request_for(source).model_dump(mode="json")
    with pytest.raises(ValidationError):
        NativePageRequest.model_validate({**payload, "derivation": "model_emission"})
    payload["claims"][0]["typed_value"] = {"amount": "0.01"}
    with pytest.raises(ValidationError):
        NativePageRequest.model_validate(payload)
    claims = normalize_page_claims(binding, NativeClaimConfiguration(), source, request_for(source))
    value = claims[0].model_dump(mode="json")
    value["typed_value"]["amount"] = "0.01"
    with pytest.raises(ValidationError):
        NativeClaim.model_validate(value)


@pytest.mark.parametrize(
    "defect",
    [
        "foreign_element",
        "span",
        "native_origin",
        "duplicate_key",
        "unknown_invoice_key",
        "unknown_family",
        "bare_family",
        "wrong_type",
    ],
)
def test_anchor_origin_registry_and_physical_key_validation(defect):
    binding, source = pure_source()
    payload = request_for(source).model_dump(mode="json")
    if defect == "foreign_element":
        payload["claims"][0]["anchor"]["element_id"] = str(uuid4())
    elif defect == "span":
        payload["claims"][0]["anchor"]["text_end"] = 10000
    elif defect == "duplicate_key":
        payload["claims"].append(payload["claims"][0])
    elif defect == "unknown_invoice_key":
        payload["claims"][0]["canonical_key"] = "invoice.unknown"
    elif defect == "unknown_family":
        payload["claims"][0]["canonical_key"] = "unregistered.line_item.amount"
    elif defect == "bare_family":
        payload["claims"][0]["canonical_key"] = "invoice"
    elif defect == "wrong_type":
        payload["claims"][0]["value_type"] = "date"
    else:
        page = source.structure.pages[0]
        page = page.model_copy(
            update={
                "elements": tuple(
                    e.model_copy(update={"text_origin": "pdf_native"}) for e in page.elements
                )
            }
        )
        source = replace(source, structure=source.structure.model_copy(update={"pages": (page,)}))
    with pytest.raises(NativeClaimError):
        normalize_page_claims(
            binding, NativeClaimConfiguration(), source, NativePageRequest.model_validate(payload)
        )


def test_partial_source_cannot_claim_complete_inventory():
    binding, source = pure_source(state="partial")
    with pytest.raises(NativeClaimError):
        normalize_page_claims(binding, NativeClaimConfiguration(), source, request_for(source))
    request = request_for(source).model_copy(
        update={"disposition": "partial", "reasons": ("source_incomplete",)}
    )
    assert normalize_page_claims(binding, NativeClaimConfiguration(), source, request)


def test_diagnostic_rebuild_does_not_reinterpret_newer_registry(monkeypatch):
    from lib.extraction.claim_registry import CLAIM_FAMILY_REGISTRIES

    binding, source = pure_source()
    claims = normalize_page_claims(binding, NativeClaimConfiguration(), source, request_for(source))
    before = diagnostic_projection(claims)
    monkeypatch.setitem(
        CLAIM_FAMILY_REGISTRIES,
        "invoice",
        replace(CLAIM_FAMILY_REGISTRIES["invoice"], required_keys=("invoice.new_requirement",)),
    )
    assert diagnostic_projection(claims) == before
    assert before["required_key_evaluation"] == "not_evaluated"
