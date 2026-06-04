from __future__ import annotations

from datetime import date

from lib.extraction.candidate_deduplication import (
    dedupe_line_item_candidates,
    dedupe_observation_candidates,
)
from lib.extraction.models import LineItemCandidateFact, ObservationCandidateFact


def test_candidate_deduplication_prefers_rich_line_items_over_sparse_duplicates() -> None:
    sparse = LineItemCandidateFact(
        line_item_type="invoice_item",
        ordinal=7,
        description="Tire service",
        evidence=[],
    )
    rich = LineItemCandidateFact(
        line_item_type="invoice_item",
        ordinal=2,
        description="Tire service",
        evidence=[{"page_number": 1, "table_id": "table-1", "row_index": 2}],
        service_date=date(2023, 4, 25),
        net_amount=127.50,
        currency="USD",
    )
    other = LineItemCandidateFact(
        line_item_type="invoice_item",
        ordinal=3,
        description="Oil",
        evidence=[],
        net_amount=51.00,
        currency="USD",
    )

    candidates = dedupe_line_item_candidates([sparse, rich, other])

    assert [(item.ordinal, item.description, item.net_amount) for item in candidates] == [
        (1, "Tire service", 127.50),
        (2, "Oil", 51.00),
    ]


def test_candidate_deduplication_collapses_equivalent_observations() -> None:
    first = ObservationCandidateFact(
        observation_family="vehicle",
        field_name="part_number",
        value_type="string",
        value="TIRE PR",
        evidence=[],
    )
    duplicate = ObservationCandidateFact(
        observation_family="vehicle",
        field_name=" part_number ",
        value_type="string",
        value=" tire pr ",
        evidence=[{"page_number": 1}],
    )
    distinct = ObservationCandidateFact(
        observation_family="vehicle",
        field_name="part_number",
        value_type="string",
        value="AXLE OIL",
        evidence=[],
    )

    candidates = dedupe_observation_candidates([first, duplicate, distinct])

    assert [item.value for item in candidates] == ["TIRE PR", "AXLE OIL"]
