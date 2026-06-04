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


def test_candidate_deduplication_preserves_same_line_item_from_distinct_rows() -> None:
    first = LineItemCandidateFact(
        line_item_type="invoice_item",
        ordinal=1,
        description="Monthly service fee",
        net_amount=99.00,
        currency="USD",
        evidence=[
            {
                "page_number": 1,
                "semantic_region_id": "region-1",
                "table_id": "table-1",
                "row_index": 1,
            }
        ],
    )
    second = LineItemCandidateFact(
        line_item_type="invoice_item",
        ordinal=2,
        description="Monthly service fee",
        net_amount=99.00,
        currency="USD",
        evidence=[
            {
                "page_number": 1,
                "semantic_region_id": "region-1",
                "table_id": "table-1",
                "row_index": 2,
            }
        ],
    )

    candidates = dedupe_line_item_candidates([first, second])

    assert [
        (item.ordinal, item.description, item.evidence[0]["row_index"]) for item in candidates
    ] == [
        (1, "Monthly service fee", 1),
        (2, "Monthly service fee", 2),
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


def test_candidate_deduplication_preserves_same_observation_from_distinct_regions() -> None:
    first = ObservationCandidateFact(
        observation_family="vehicle",
        field_name="service_note",
        value_type="string",
        value="Customer requested inspection",
        evidence=[{"page_number": 1, "semantic_region_id": "region-1"}],
    )
    second = ObservationCandidateFact(
        observation_family="vehicle",
        field_name="service_note",
        value_type="string",
        value="Customer requested inspection",
        evidence=[{"page_number": 2, "semantic_region_id": "region-2"}],
    )

    candidates = dedupe_observation_candidates([first, second])

    assert [(item.value, item.evidence[0]["semantic_region_id"]) for item in candidates] == [
        ("Customer requested inspection", "region-1"),
        ("Customer requested inspection", "region-2"),
    ]
