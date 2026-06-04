from __future__ import annotations

import re
from collections.abc import Collection
from typing import Any


def normalized_quality_key(value: object) -> str:
    text = str(value or "").strip().replace("-", "_").replace(" ", "_")
    text = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", text)
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    return "_".join(part for part in text.lower().split("_") if part)


PROMPT_ECHO_PATTERNS = (
    "identify and extract",
    "extract the schema",
    "extruct the schema",
    "tabls schema",
    "table schema",
    "tables in the image",
    "reading order",
    "return only json",
    "matching the schema",
)
SCHEMA_ARTIFACT_KEYS = frozenset(
    {
        "$schema",
        "json_schema",
        "response_format",
        "system_prompt",
        "tool_schema",
    }
)
SCHEMA_ARTIFACT_VALUES = (
    "$schema",
    "json schema",
    "response_format",
    "tool schema",
)
SCHEMA_ARTIFACT_VALUE_TOKENS = frozenset(
    {
        "$schema",
        "json_schema",
        "response_format",
        "system_prompt",
        "tool_schema",
    }
)
SCHEMA_ARTIFACT_TOKENS = SCHEMA_ARTIFACT_KEYS | SCHEMA_ARTIFACT_VALUE_TOKENS
COMPACT_SCHEMA_ARTIFACT_TOKENS = frozenset(
    token.replace("_", "") for token in SCHEMA_ARTIFACT_TOKENS
)
PLACEHOLDER_FIELD_NAMES = frozenset(
    {
        "visible_field",
        "field",
        "key",
        "value",
    }
)
PLACEHOLDER_VALUES = frozenset(
    {
        "",
        "--",
        "null",
        "none",
        "n/a",
        "na",
        "field",
        "key",
        "missing",
        "not applicable",
        "not available",
        "not found",
        "not provided",
        "placeholder",
        "tbd",
        "unknown",
        "visible_field",
        "visible value",
        "example value",
        "<placeholder>",
    }
)
NORMALIZED_PLACEHOLDER_VALUES = frozenset(
    normalized_quality_key(value) for value in PLACEHOLDER_VALUES
)
NORMALIZED_PLACEHOLDER_FIELD_NAMES = frozenset(
    normalized_quality_key(value) for value in PLACEHOLDER_FIELD_NAMES
)
NORMALIZED_PLACEHOLDER_TOKENS = NORMALIZED_PLACEHOLDER_VALUES | NORMALIZED_PLACEHOLDER_FIELD_NAMES
COMPACT_NORMALIZED_PLACEHOLDER_TOKENS = frozenset(
    token.replace("_", "") for token in NORMALIZED_PLACEHOLDER_TOKENS
)
PRIMARY_VALUE_KEYS = frozenset(
    {
        "account_holder",
        "account_number",
        "address",
        "allowed_amount",
        "amount",
        "amount_due",
        "amount_paid",
        "application_name",
        "auth_code",
        "auth_mode",
        "balance_due",
        "billed_amount",
        "buyer_name",
        "card_number",
        "claim_number",
        "closing_date",
        "code",
        "contact_type",
        "counterparty_name",
        "customer_name",
        "date",
        "deadline",
        "decision",
        "description",
        "display_name",
        "dispute_reason",
        "escrow_balance",
        "fax",
        "field_name",
        "field_value",
        "file_number",
        "insurance_amount",
        "invoice_no",
        "invoice_number",
        "issue_date",
        "issued_date",
        "key",
        "labor_operation",
        "line_total",
        "loan_number",
        "mailing_address",
        "merchant",
        "merchant_id",
        "merchant_name",
        "name",
        "order_date",
        "order_number",
        "paid_amount",
        "paid_date",
        "part_number",
        "patient_name",
        "patient_responsibility",
        "payer_name",
        "payment_amount",
        "payment_method",
        "phone",
        "policy_number",
        "procedure_code",
        "property_address",
        "provider_name",
        "quantity",
        "seller",
        "seller_name",
        "service_address",
        "service_date",
        "service_description",
        "servicer_name",
        "sku",
        "statement_date",
        "subtotal",
        "tax",
        "tax_amount",
        "tax_total",
        "terminal_id",
        "text",
        "tip",
        "title_company",
        "total",
        "total_amount",
        "total_patient_responsibility",
        "transaction_amount",
        "transaction_date",
        "unit",
        "unit_price",
        "url",
        "value",
        "vendor_name",
    }
)
LINE_ITEM_VALUE_KEYS = PRIMARY_VALUE_KEYS | frozenset(
    {
        "allowed_amount",
        "billed_amount",
        "category_hint",
        "code",
        "code_system",
        "currency",
        "discount_amount",
        "gross_amount",
        "line_item_type",
        "net_amount",
        "paid_amount",
        "patient_responsibility",
        "procedure_code",
        "quantity",
        "service_date",
        "tax_amount",
        "unit",
        "unit_price",
    }
)


def contains_prompt_echo(value: object) -> bool:
    text = str(value or "").lower()
    token = _normalized_key(value)
    return any(pattern in text for pattern in PROMPT_ECHO_PATTERNS) or any(
        _normalized_key(pattern) in token for pattern in PROMPT_ECHO_PATTERNS
    )


def contains_prompt_or_schema_artifact(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if _is_schema_artifact_key(key) or contains_prompt_echo(key):
                return True
            if contains_prompt_or_schema_artifact(item):
                return True
        return False
    if isinstance(value, list | tuple | set):
        return any(contains_prompt_or_schema_artifact(item) for item in value)
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    normalized_token = _normalized_key(value)
    if normalized in {"<json_schema>", "json_schema", "response_format"}:
        return True
    if _is_schema_artifact_token(normalized_token):
        return True
    if contains_prompt_echo(value):
        return True
    compact_token = normalized_token.replace("_", "")
    return (
        any(token in normalized for token in SCHEMA_ARTIFACT_VALUES)
        or any(token in normalized_token for token in SCHEMA_ARTIFACT_TOKENS)
        or any(token in compact_token for token in COMPACT_SCHEMA_ARTIFACT_TOKENS)
    )


def contains_placeholder_value(
    value: object,
    *,
    key: object | None = None,
    value_keys: Collection[str] | None = PRIMARY_VALUE_KEYS,
    reject_null_leaves: bool = True,
) -> bool:
    return contains_placeholder_value_for_keys(
        value,
        key=key,
        value_keys=value_keys,
        reject_null_leaves=reject_null_leaves,
    )


def contains_placeholder_value_any_key(value: object) -> bool:
    return contains_placeholder_value_for_keys(
        value,
        value_keys=None,
        reject_null_leaves=True,
    )


def contains_placeholder_value_for_keys(
    value: object,
    *,
    key: object | None = None,
    value_keys: Collection[str] | None,
    reject_null_leaves: bool,
) -> bool:
    key_is_value = (
        value_keys is None
        or key is None
        or matches_normalized_key(
            key,
            value_keys,
        )
    )
    if value is None:
        return reject_null_leaves and key_is_value
    if isinstance(value, str):
        return key_is_value and is_placeholder_token(value)
    if isinstance(value, dict):
        return any(
            contains_placeholder_value_for_keys(
                item,
                key=item_key,
                value_keys=value_keys,
                reject_null_leaves=reject_null_leaves,
            )
            for item_key, item in value.items()
        )
    if isinstance(value, list | tuple | set):
        return any(
            contains_placeholder_value_for_keys(
                item,
                key=key,
                value_keys=value_keys,
                reject_null_leaves=reject_null_leaves,
            )
            for item in value
        )
    return False


def is_placeholder_token(value: object) -> bool:
    normalized = normalized_quality_key(value)
    return (
        normalized in NORMALIZED_PLACEHOLDER_TOKENS
        or normalized.replace("_", "") in COMPACT_NORMALIZED_PLACEHOLDER_TOKENS
    )


def matches_normalized_key(key: object, candidates: Collection[str]) -> bool:
    normalized = normalized_quality_key(key)
    compact = normalized.replace("_", "")
    return normalized in candidates or compact in {
        candidate.replace("_", "") for candidate in candidates
    }


def _is_schema_artifact_key(value: object) -> bool:
    normalized = _normalized_key(value)
    return _is_schema_artifact_token(normalized)


def _is_schema_artifact_token(value: str) -> bool:
    return (
        value in SCHEMA_ARTIFACT_TOKENS or value.replace("_", "") in COMPACT_SCHEMA_ARTIFACT_TOKENS
    )


def _normalized_key(value: object) -> str:
    return normalized_quality_key(value)
