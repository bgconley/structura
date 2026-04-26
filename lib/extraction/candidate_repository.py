from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.extraction.errors import ExtractionRepositoryError
from lib.extraction.models import CandidateFact, LineItemCandidateFact


def insert_field_candidate(
    cur: Any,
    document_id: UUID,
    extraction_id: UUID,
    source_engine: str,
    candidate: CandidateFact,
) -> dict[str, Any]:
    typed = typed_value_columns(candidate.value_type, candidate.value)
    cur.execute(
        """
        INSERT INTO field_candidates
          (
            document_id, extraction_id, field_path, ordinal, source_engine,
            source_ref, value_type, text_value, integer_value, numeric_value,
            boolean_value, date_value, timestamp_value, json_value, currency_code,
            confidence, authority_weight, evidence_json, validation_json, status
          )
        VALUES (
          %s, %s, %s, %s, %s, %s, %s,
          %s, %s, %s, %s, %s, %s, %s::jsonb,
          %s, %s, %s, %s::jsonb, %s::jsonb, %s
        )
        RETURNING *
        """,
        (
            document_id,
            extraction_id,
            candidate.field_path,
            candidate.ordinal,
            source_engine,
            f"{source_engine}:{extraction_id}",
            candidate.value_type,
            typed["text_value"],
            typed["integer_value"],
            typed["numeric_value"],
            typed["boolean_value"],
            typed["date_value"],
            typed["timestamp_value"],
            Jsonb(typed["json_value"]),
            candidate.currency,
            candidate.confidence,
            candidate.authority_weight,
            Jsonb(candidate.evidence),
            Jsonb(candidate.validation),
            candidate.status,
        ),
    )
    row = cur.fetchone()
    if not row:
        raise ExtractionRepositoryError("Field candidate insert failed.")
    return cast(dict[str, Any], row)


def insert_line_item_candidate(
    cur: Any,
    document_id: UUID,
    extraction_id: UUID,
    source_engine: str,
    candidate: LineItemCandidateFact,
) -> None:
    cur.execute(
        """
        INSERT INTO line_item_candidates
          (
            document_id, extraction_id, source_engine, line_item_type, candidate_group,
            ordinal, code, code_system, service_date, description, quantity, unit,
            unit_price, gross_amount, discount_amount, tax_amount, net_amount,
            currency_code, category_hint, confidence, authority_weight, evidence_json,
            validation_json, status
          )
        VALUES (
          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s
        )
        """,
        (
            document_id,
            extraction_id,
            source_engine,
            candidate.line_item_type,
            candidate.candidate_group,
            candidate.ordinal,
            candidate.code,
            candidate.code_system,
            candidate.service_date,
            candidate.description,
            candidate.quantity,
            candidate.unit,
            candidate.unit_price,
            candidate.gross_amount,
            candidate.discount_amount,
            candidate.tax_amount,
            candidate.net_amount,
            candidate.currency,
            candidate.category_hint,
            candidate.confidence,
            candidate.authority_weight,
            Jsonb(candidate.evidence),
            Jsonb(candidate.validation),
            candidate.status,
        ),
    )


def typed_value_columns(value_type: str, value: Any) -> dict[str, Any]:
    if value_type == "money" and isinstance(value, Mapping):
        return {
            **_empty_value_columns(),
            "numeric_value": Decimal(str(value.get("amount"))),
            "json_value": dict(value),
        }
    if value_type == "date":
        return {**_empty_value_columns(), "date_value": value}
    if value_type == "integer":
        return {**_empty_value_columns(), "integer_value": int(value)}
    if value_type == "number":
        return {**_empty_value_columns(), "numeric_value": Decimal(str(value))}
    if value_type == "boolean":
        return {**_empty_value_columns(), "boolean_value": bool(value)}
    if value_type == "json":
        return {**_empty_value_columns(), "json_value": value}
    return {**_empty_value_columns(), "text_value": str(value)}


def canonical_column_values(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "text_value": row.get("text_value"),
        "integer_value": row.get("integer_value"),
        "numeric_value": row.get("numeric_value"),
        "boolean_value": row.get("boolean_value"),
        "date_value": row.get("date_value"),
        "timestamp_value": row.get("timestamp_value"),
        "json_value": row.get("json_value"),
        "currency_code": row.get("currency_code"),
    }


def value_from_candidate_row(row: Mapping[str, Any]) -> Any:
    value_type = row.get("value_type")
    if value_type == "money":
        return row.get("json_value") or {
            "amount": float(row["numeric_value"]),
            "currency": row.get("currency_code"),
        }
    if value_type == "date":
        value = row.get("date_value")
        return value.isoformat() if isinstance(value, date) else value
    if value_type == "integer":
        return row.get("integer_value")
    if value_type == "number":
        value = row.get("numeric_value")
        return float(value) if value is not None else None
    if value_type == "boolean":
        return row.get("boolean_value")
    if value_type == "json":
        return row.get("json_value")
    return row.get("text_value")


def candidate_value_json(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "valueType": candidate["value_type"],
        "value": value_from_candidate_row(candidate),
        "currency": candidate.get("currency_code"),
    }


def _empty_value_columns() -> dict[str, Any]:
    return {
        "text_value": None,
        "integer_value": None,
        "numeric_value": None,
        "boolean_value": None,
        "date_value": None,
        "timestamp_value": None,
        "json_value": None,
    }
