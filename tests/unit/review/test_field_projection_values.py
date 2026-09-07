from copy import deepcopy
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from lib.fact_authority.projection_values import (
    COUNTERPARTY_PATHS,
    accepted_facts_digest,
    owned_scalar,
    scalar_selection,
    selected_total,
)


def test_conflicting_total_pairs_are_never_combined_into_a_fabricated_amount_currency():
    rows = [
        {
            "field_path": "invoice.total_amount",
            "numeric_value": Decimal("100"),
            "currency_code": "USD",
        },
        {
            "field_path": "receipt.transaction.total",
            "numeric_value": Decimal("200"),
            "currency_code": "EUR",
        },
    ]
    assert selected_total(rows) is None
    assert selected_total([rows[0], rows[0]]) == (Decimal("100"), "USD")
    assert selected_total([{**rows[0], "numeric_value": Decimal("0")}]) == (Decimal("0"), "USD")


def test_counterparty_conflicts_are_not_resolved_by_arbitrary_sort_order():
    a = {"field_path": "invoice.seller.display_name", "text_value": "Alpha"}
    b = {"field_path": "receipt.merchant.display_name", "text_value": "Zulu"}
    assert scalar_selection([a, b], COUNTERPARTY_PATHS, "text_value") is None
    assert scalar_selection([a, a], COUNTERPARTY_PATHS, "text_value") == "Alpha"


def test_owned_rollup_can_clear_but_unknown_legacy_and_explicit_manual_null_are_preserved():
    assert owned_scalar(
        current="Old fact",
        proposed=None,
        previous={"ownership": "accepted_fact", "value": "Old fact"},
    ) == {"ownership": "accepted_fact", "value": None}
    assert owned_scalar(current="Unestablished", proposed="Model guess", previous=None) == {
        "ownership": "unestablished",
        "value": "Unestablished",
    }
    assert owned_scalar(
        current=date(2020, 1, 2),
        proposed=date(2025, 1, 2),
        previous=None,
        manual_present=True,
        manual_value=None,
    ) == {"ownership": "manual", "value": None}
    assert owned_scalar(
        current="New manual label",
        proposed="Model guess",
        previous={"ownership": "accepted_fact", "value": "Old fact"},
    ) == {"ownership": "unestablished", "value": "New manual label"}


@pytest.mark.parametrize(
    "column,value",
    [
        ("text_value", "New accepted fact"),
        ("evidence_json", [{"sourceText": "New locator"}]),
        ("decision_revision", uuid4()),
        ("selected_candidate_id", uuid4()),
        ("review_status", "user_corrected"),
    ],
)
def test_accepted_field_fingerprint_tracks_truth_provenance_and_decision(column, value):
    original = {
        "id": uuid4(),
        "field_path": "invoice.purchase_order",
        "ordinal": 1,
        "text_value": "Accepted fact",
        "decision_revision": uuid4(),
    }
    changed = deepcopy(original)
    changed[column] = value
    assert accepted_facts_digest([original]) != accepted_facts_digest([changed])
    other = {**original, "id": uuid4(), "ordinal": 2}
    assert accepted_facts_digest([original, other]) == accepted_facts_digest([other, original])
    # An unrelated workflow timestamp does not invent an accepted-fact change.
    assert accepted_facts_digest([original]) == accepted_facts_digest(
        [{**original, "updated_at": "later"}]
    )
