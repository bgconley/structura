"""Frozen receipt/invoice/EOB obligations, including app-spec gaps in legacy keys.

These are model-output obligations, not an accepted-fact projection or a promise
that every optional value exists on a particular page.
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal

ValueType = Literal[
    "money",
    "date",
    "time",
    "quantity",
    "number",
    "identifier",
    "identifiers",
    "party",
    "enum",
    "text",
    "boolean",
]
REGISTRY_VERSION = "page-claim-obligations-v2"


@dataclass(frozen=True)
class FieldRule:
    key: str
    value_type: ValueType
    scope: Literal["field", "line"]
    obligation: Literal["required", "where_present"]
    source_path: str


def _fields(
    family: str, records: tuple[tuple[str, ValueType, str, bool], ...]
) -> tuple[FieldRule, ...]:
    return tuple(
        FieldRule(
            f"{family}.{key}", kind, "field", "required" if required else "where_present", path
        )
        for key, kind, path, required in records
    )


def _party(family: str, role: str) -> tuple[FieldRule, ...]:
    return _fields(
        family,
        (
            (f"{role}.display_name", "party", f"{role}.display_name", True),
            (f"{role}.address", "text", f"{role}.address", False),
            (f"{role}.identifiers", "text", f"{role}.identifiers", False),
            (f"{role}.normalized_name", "text", f"{role}.normalized_name", False),
            (f"{role}.party_type", "enum", f"{role}.party_type", False),
        ),
    )


def _lines(
    family: str, records: tuple[tuple[str, ValueType, str, bool], ...]
) -> tuple[FieldRule, ...]:
    return tuple(
        FieldRule(
            f"{family}.line_item.{key}",
            kind,
            "line",
            "required" if required else "where_present",
            path,
        )
        for key, kind, path, required in records
    )


RECEIPT_RULES = (
    _party("receipt", "merchant")
    + _fields(
        "receipt",
        (
            ("transaction.date_local", "date", "transaction.date_local", True),
            ("transaction.time_local", "time", "transaction.time_local", True),
            ("transaction.register_id", "identifier", "transaction.register_id", False),
            ("transaction.receipt_number", "identifier", "transaction.receipt_number", False),
            ("transaction.payment_method", "text", "transaction.payment_method", True),
            ("transaction.payment_reference", "identifier", "transaction.payment_reference", False),
            ("transaction.subtotal", "money", "transaction.subtotal", True),
            ("transaction.tax", "money", "transaction.tax", True),
            ("transaction.tip", "money", "transaction.tip", False),
            ("transaction.discount_total", "money", "transaction.discount_total", False),
            ("transaction.total", "money", "transaction.total", True),
        ),
    )
    + _lines(
        "receipt",
        (
            ("description", "text", "line_items[].description", True),
            ("code", "identifier", "line_items[].sku", False),
            ("quantity", "quantity", "line_items[].quantity", False),
            ("unit", "text", "line_items[].unit", False),
            ("unit_price", "money", "line_items[].unit_price", False),
            ("amount", "money", "line_items[].amount", True),
            ("discount", "money", "line_items[].discount", False),
            ("tax_category_hint", "text", "line_items[].tax_category_hint", False),
            ("category_hint", "text", "line_items[].category_hint", False),
        ),
    )
)

INVOICE_RULES = (
    _party("invoice", "seller")
    + _party("invoice", "buyer")
    + _fields(
        "invoice",
        (
            ("invoice_number", "identifier", "invoice.invoice_number", True),
            ("purchase_order_number", "identifier", "invoice.purchase_order_number", False),
            ("issue_date", "date", "invoice.issued_on", True),
            ("due_date", "date", "invoice.due_on", True),
            ("terms", "text", "invoice.terms", False),
            ("service_period_start", "date", "invoice.service_period_start", False),
            ("service_period_end", "date", "invoice.service_period_end", False),
            ("remittance.instructions", "text", "app_spec.6.4.invoice.remittance", True),
            ("remittance.payee", "party", "app_spec.6.4.invoice.remittance.payee", False),
            ("remittance.address", "text", "app_spec.6.4.invoice.remittance.address", False),
            (
                "remittance.reference",
                "identifier",
                "app_spec.6.4.invoice.remittance.reference",
                False,
            ),
            ("subtotal", "money", "totals.subtotal", False),
            ("tax_total", "money", "totals.tax_total", False),
            ("discount_total", "money", "totals.discount_total", False),
            ("shipping_total", "money", "totals.shipping_total", False),
            ("total_amount", "money", "totals.total", True),
            ("amount_paid", "money", "totals.amount_paid", False),
            ("balance_due", "money", "totals.balance_due", False),
        ),
    )
    + _lines(
        "invoice",
        (
            ("description", "text", "line_items[].description", True),
            ("service_date", "date", "line_items[].service_date", False),
            ("quantity", "quantity", "line_items[].quantity", False),
            ("unit", "text", "line_items[].unit", False),
            ("unit_price", "money", "line_items[].unit_price", False),
            ("amount", "money", "line_items[].amount", True),
            ("tax_amount", "money", "line_items[].tax_amount", False),
            ("gl_hint", "text", "line_items[].gl_hint", False),
            ("code", "identifier", "legacy_registry.line_item.code", False),
            ("gross_amount", "money", "legacy_registry.line_item.gross_amount", False),
            ("category_hint", "text", "legacy_registry.line_item.category_hint", False),
        ),
    )
)

EOB_RULES = (
    _party("medical_eob", "payer")
    + _party("medical_eob", "patient")
    + _party("medical_eob", "provider")
    + _fields(
        "medical_eob",
        (
            ("claim_number", "identifier", "claim.claim_number", True),
            ("received_on", "date", "claim.received_on", False),
            ("processed_on", "date", "claim.processed_on", True),
            ("group_number", "identifier", "claim.group_number", False),
            ("member_id", "identifier", "claim.member_id", False),
            ("total_billed", "money", "financial_summary.total_billed", False),
            ("total_allowed", "money", "financial_summary.total_allowed", False),
            ("total_plan_paid", "money", "financial_summary.total_plan_paid", False),
            (
                "total_patient_responsibility",
                "money",
                "financial_summary.total_patient_responsibility",
                False,
            ),
            ("total_deductible", "money", "app_spec.6.4.medical_eob.deductible", False),
            ("total_coinsurance", "money", "app_spec.6.4.medical_eob.coinsurance", False),
            ("total_copay", "money", "app_spec.6.4.medical_eob.copay", False),
        ),
    )
) + _lines(
    "medical_eob",
    (
        ("description", "text", "service_lines[].service_description", True),
        ("service_date", "date", "service_lines[].service_date", False),
        ("service_end_date", "date", "service_lines[].service_end_date", False),
        ("code", "identifier", "service_lines[].procedure_code", False),
        ("modifiers", "identifiers", "app_spec.6.4.medical_eob.modifiers", False),
        ("diagnosis_code", "identifier", "service_lines[].diagnosis_code", False),
        ("revenue_code", "identifier", "service_lines[].revenue_code", False),
        ("place_of_service", "identifier", "service_lines[].place_of_service", False),
        ("quantity", "quantity", "service_lines[].units", False),
        ("gross_amount", "money", "service_lines[].billed_amount", True),
        ("allowed_amount", "money", "service_lines[].allowed_amount", True),
        ("plan_paid", "money", "service_lines[].plan_paid", True),
        ("amount", "money", "service_lines[].patient_responsibility", True),
        ("deductible", "money", "service_lines[].deductible", False),
        ("copay", "money", "service_lines[].copay", False),
        ("coinsurance", "money", "service_lines[].coinsurance", False),
        ("category_hint", "text", "service_lines[].adjustment_reason", False),
        ("remark_codes", "identifiers", "service_lines[].remark_codes", False),
    ),
)

FIELD_RULES = RECEIPT_RULES + INVOICE_RULES + EOB_RULES
RULE_BY_KEY = MappingProxyType({rule.key: rule for rule in FIELD_RULES})
if len(RULE_BY_KEY) != len(FIELD_RULES):
    raise RuntimeError("Frozen claim registry contains duplicate keys.")


def key_schema(schema: dict[str, Any]) -> None:
    """Publish the same closed key inventory in model-facing JSON Schema."""
    schema["enum"] = sorted(RULE_BY_KEY)


def family_rules(family: str, scope: Literal["field", "line"]) -> tuple[FieldRule, ...]:
    return tuple(
        rule for rule in FIELD_RULES if rule.key.startswith(family + ".") and rule.scope == scope
    )
