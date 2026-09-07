"""Deterministic accepted-fact fingerprints and conservative scalar rollup ownership."""

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

COUNTERPARTY_PATHS = (
    "receipt.merchant.display_name",
    "invoice.seller.display_name",
    "medical_eob.provider.display_name",
    "medical_eob.payer.display_name",
)
DATE_PATHS = ("receipt.transaction.date_local", "invoice.issue_date")
TOTAL_PATHS = (
    "receipt.transaction.total",
    "invoice.total_amount",
    "medical_eob.total_patient_responsibility",
)
FACT_COLUMNS = (
    "id",
    "field_path",
    "ordinal",
    "value_type",
    "text_value",
    "integer_value",
    "numeric_value",
    "boolean_value",
    "date_value",
    "timestamp_value",
    "json_value",
    "currency_code",
    "evidence_json",
    "selected_candidate_id",
    "source_kind",
    "review_status",
    "decision_revision",
)


def json_scalar(value: object) -> str:
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, Decimal | UUID):
        return str(value)
    raise TypeError("Unsupported projection value.")


def snapshot_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, default=json_scalar, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def accepted_facts_digest(rows: Sequence[Mapping[str, Any]]) -> str:
    return snapshot_digest(
        {
            "schemaVersion": "accepted_fields.v1",
            "fields": [
                {key: row.get(key) for key in FACT_COLUMNS}
                for row in sorted(rows, key=lambda row: (row["field_path"], row["ordinal"]))
            ],
        }
    )


def scalar_selection(
    rows: Sequence[Mapping[str, Any]], paths: tuple[str, ...], column: str
) -> object:
    # Repeated identical values are usable; conflicting ordinals/families are
    # not resolved by arbitrary lexical or numerical MAX.
    values = [row[column] for row in rows if row["field_path"] in paths and row[column] is not None]
    unique = {json.dumps(value, default=json_scalar, sort_keys=True) for value in values}
    return values[0] if len(unique) == 1 else None


def selected_total(rows: Sequence[Mapping[str, Any]]) -> tuple[object, str | None] | None:
    pairs = {
        (row["numeric_value"], row["currency_code"])
        for row in rows
        if row["field_path"] in TOTAL_PATHS and row["numeric_value"] is not None
    }
    return next(iter(pairs)) if len(pairs) == 1 else None


def owned_scalar(
    *,
    current: object,
    proposed: object,
    previous: Mapping[str, Any] | None,
    manual_present: bool = False,
    manual_value: object = None,
) -> dict[str, object]:
    current_json = json.loads(json.dumps(current, default=json_scalar))
    proposed_json = json.loads(json.dumps(proposed, default=json_scalar))
    if manual_present:
        return {"ownership": "manual", "value": manual_value}
    if current is None or (
        previous
        and previous.get("ownership") == "accepted_fact"
        and previous.get("value") == current_json
    ):
        return {"ownership": "accepted_fact", "value": proposed_json}
    return {"ownership": "unestablished", "value": current_json}
