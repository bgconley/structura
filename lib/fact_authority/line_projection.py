"""Versioned selected-field and selected-line basis; scalar rollups remain field-owned."""

from collections.abc import Mapping, Sequence
from typing import Any

from lib.fact_authority.projection_values import FACT_COLUMNS, snapshot_digest

BASIS_VERSION = "accepted_fields_and_lines.v1"
LINE_COLUMNS = (
    "id",
    "line_item_type",
    "ordinal",
    "selected_candidate_id",
    "code",
    "code_system",
    "service_date",
    "description",
    "quantity",
    "unit",
    "unit_price",
    "gross_amount",
    "discount_amount",
    "tax_amount",
    "net_amount",
    "allowed_amount",
    "plan_paid_amount",
    "currency_code",
    "category_hint",
    "evidence_json",
    "source_kind",
    "review_status",
    "decision_revision",
)


def selected_facts_digest(
    fields: Sequence[Mapping[str, Any]], lines: Sequence[Mapping[str, Any]]
) -> str:
    return snapshot_digest(
        {
            "schemaVersion": BASIS_VERSION,
            "fields": [
                {key: row.get(key) for key in FACT_COLUMNS}
                for row in sorted(fields, key=lambda row: (row["field_path"], row["ordinal"]))
            ],
            "lines": [
                {key: row.get(key) for key in LINE_COLUMNS}
                for row in sorted(lines, key=lambda row: (row["line_item_type"], row["ordinal"]))
            ],
        }
    )
