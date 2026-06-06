from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClaimFieldProjection:
    canonical_key: str
    container: str
    field_name: str
    value_types: tuple[str, ...]


@dataclass(frozen=True)
class ClaimLineItemProjection:
    canonical_prefix: str
    field_map: dict[str, str]
    value_types: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class ClaimArithmeticInvariant:
    target_key: str
    addend_keys: tuple[str, ...]
    reason_code: str
    currency_reason_code: str = "cross_field_currency_conflict"


@dataclass(frozen=True)
class ClaimLineItemSumInvariant:
    target_key: str
    line_item_field: str
    reason_code: str
    currency_reason_code: str = "cross_field_currency_conflict"


@dataclass(frozen=True)
class ClaimFamilyRegistry:
    family: str
    field_projections: tuple[ClaimFieldProjection, ...]
    line_item_projection: ClaimLineItemProjection | None = None
    required_keys: tuple[str, ...] = ()
    arithmetic_invariants: tuple[ClaimArithmeticInvariant, ...] = ()
    line_item_sum_invariants: tuple[ClaimLineItemSumInvariant, ...] = ()


INVOICE_CLAIM_REGISTRY = ClaimFamilyRegistry(
    family="invoice",
    field_projections=(
        ClaimFieldProjection(
            "invoice.invoice_number", "invoice", "invoice_number", ("identifier", "text")
        ),
        ClaimFieldProjection("invoice.issue_date", "invoice", "issued_on", ("date",)),
        ClaimFieldProjection("invoice.due_date", "invoice", "due_on", ("date",)),
        ClaimFieldProjection("invoice.subtotal", "totals", "subtotal", ("money",)),
        ClaimFieldProjection("invoice.tax_total", "totals", "tax_total", ("money",)),
        ClaimFieldProjection("invoice.total_amount", "totals", "total", ("money",)),
        ClaimFieldProjection("invoice.balance_due", "totals", "balance_due", ("money",)),
        ClaimFieldProjection("invoice.amount_paid", "totals", "amount_paid", ("money",)),
    ),
    required_keys=("invoice.invoice_number", "invoice.total_amount"),
    arithmetic_invariants=(
        ClaimArithmeticInvariant(
            target_key="invoice.total_amount",
            addend_keys=("invoice.subtotal", "invoice.tax_total"),
            reason_code="cross_field_arithmetic_conflict",
        ),
    ),
    line_item_sum_invariants=(
        ClaimLineItemSumInvariant(
            target_key="invoice.subtotal",
            line_item_field="amount",
            reason_code="line_item_sum_conflict",
        ),
    ),
    line_item_projection=ClaimLineItemProjection(
        canonical_prefix="invoice.line_item.",
        field_map={
            "description": "description",
            "code": "code",
            "quantity": "quantity",
            "unit": "unit",
            "unit_price": "unit_price",
            "gross_amount": "gross_amount",
            "tax_amount": "tax_amount",
            "amount": "amount",
            "service_date": "service_date",
            "category_hint": "category_hint",
        },
        value_types={
            "description": ("text",),
            "code": ("identifier", "text"),
            "quantity": ("number", "quantity"),
            "unit": ("text",),
            "unit_price": ("money",),
            "gross_amount": ("money",),
            "tax_amount": ("money",),
            "amount": ("money",),
            "service_date": ("date",),
            "category_hint": ("text",),
        },
    ),
)

RECEIPT_CLAIM_REGISTRY = ClaimFamilyRegistry(
    family="receipt",
    field_projections=(
        ClaimFieldProjection(
            "receipt.merchant.display_name", "merchant", "display_name", ("party", "text")
        ),
        ClaimFieldProjection(
            "receipt.transaction.date_local", "transaction", "date_local", ("date",)
        ),
        ClaimFieldProjection("receipt.transaction.subtotal", "transaction", "subtotal", ("money",)),
        ClaimFieldProjection("receipt.transaction.tax", "transaction", "tax", ("money",)),
        ClaimFieldProjection("receipt.transaction.tip", "transaction", "tip", ("money",)),
        ClaimFieldProjection("receipt.transaction.total", "transaction", "total", ("money",)),
    ),
    arithmetic_invariants=(
        ClaimArithmeticInvariant(
            target_key="receipt.transaction.total",
            addend_keys=(
                "receipt.transaction.subtotal",
                "receipt.transaction.tax",
                "receipt.transaction.tip",
            ),
            reason_code="cross_field_arithmetic_conflict",
        ),
    ),
    line_item_sum_invariants=(
        ClaimLineItemSumInvariant(
            target_key="receipt.transaction.subtotal",
            line_item_field="amount",
            reason_code="line_item_sum_conflict",
        ),
    ),
    line_item_projection=ClaimLineItemProjection(
        canonical_prefix="receipt.line_item.",
        field_map={
            "description": "description",
            "code": "sku",
            "quantity": "quantity",
            "unit": "unit",
            "unit_price": "unit_price",
            "amount": "amount",
            "category_hint": "category_hint",
        },
        value_types={
            "description": ("text",),
            "code": ("identifier", "text"),
            "quantity": ("number", "quantity"),
            "unit": ("text",),
            "unit_price": ("money",),
            "amount": ("money",),
            "category_hint": ("text",),
        },
    ),
)

MEDICAL_EOB_CLAIM_REGISTRY = ClaimFamilyRegistry(
    family="medical_eob",
    field_projections=(
        ClaimFieldProjection(
            "medical_eob.payer.display_name", "payer", "display_name", ("party", "text")
        ),
        ClaimFieldProjection(
            "medical_eob.patient.display_name", "patient", "display_name", ("party", "text")
        ),
        ClaimFieldProjection(
            "medical_eob.provider.display_name",
            "provider",
            "display_name",
            ("party", "text"),
        ),
        ClaimFieldProjection(
            "medical_eob.claim_number", "claim", "claim_number", ("identifier", "text")
        ),
        ClaimFieldProjection("medical_eob.received_on", "claim", "received_on", ("date",)),
        ClaimFieldProjection("medical_eob.processed_on", "claim", "processed_on", ("date",)),
        ClaimFieldProjection(
            "medical_eob.group_number", "claim", "group_number", ("identifier", "text")
        ),
        ClaimFieldProjection("medical_eob.member_id", "claim", "member_id", ("identifier", "text")),
        ClaimFieldProjection(
            "medical_eob.total_billed",
            "financial_summary",
            "total_billed",
            ("money",),
        ),
        ClaimFieldProjection(
            "medical_eob.total_allowed",
            "financial_summary",
            "total_allowed",
            ("money",),
        ),
        ClaimFieldProjection(
            "medical_eob.total_plan_paid",
            "financial_summary",
            "total_plan_paid",
            ("money",),
        ),
        ClaimFieldProjection(
            "medical_eob.total_patient_responsibility",
            "financial_summary",
            "total_patient_responsibility",
            ("money",),
        ),
    ),
    line_item_projection=ClaimLineItemProjection(
        canonical_prefix="medical_eob.line_item.",
        field_map={
            "description": "service_description",
            "code": "procedure_code",
            "quantity": "units",
            "gross_amount": "billed_amount",
            "amount": "patient_responsibility",
            "service_date": "service_date",
            "category_hint": "adjustment_reason",
        },
        value_types={
            "description": ("text",),
            "code": ("identifier", "text"),
            "quantity": ("number", "quantity"),
            "gross_amount": ("money",),
            "amount": ("money",),
            "service_date": ("date",),
            "category_hint": ("text",),
        },
    ),
)

SERVICE_RECORD_CLAIM_REGISTRY = ClaimFamilyRegistry(
    family="service_record",
    field_projections=(
        ClaimFieldProjection("service_record.subtotal", "totals", "subtotal", ("money",)),
        ClaimFieldProjection("service_record.tax", "totals", "tax", ("money",)),
        ClaimFieldProjection("service_record.total", "totals", "total", ("money",)),
    ),
    line_item_projection=ClaimLineItemProjection(
        canonical_prefix="service_record.line_item.",
        field_map={
            "description": "description",
            "code": "code",
            "quantity": "quantity",
            "unit": "unit",
            "unit_price": "unit_price",
            "gross_amount": "line_total",
            "tax_amount": "tax_amount",
            "amount": "amount",
            "service_date": "service_date",
            "category_hint": "category_hint",
        },
        value_types={
            "description": ("text",),
            "code": ("identifier", "text"),
            "quantity": ("number", "quantity"),
            "unit": ("text",),
            "unit_price": ("money",),
            "gross_amount": ("money",),
            "tax_amount": ("money",),
            "amount": ("money",),
            "service_date": ("date",),
            "category_hint": ("text",),
        },
    ),
)

RETAIL_ORDER_CLAIM_REGISTRY = ClaimFamilyRegistry(
    family="retail_order",
    field_projections=(
        ClaimFieldProjection(
            "retail_order.merchant_name", "order", "merchant_name", ("party", "text")
        ),
        ClaimFieldProjection(
            "retail_order.order_number", "order", "order_number", ("identifier", "text")
        ),
        ClaimFieldProjection("retail_order.order_date", "order", "order_date", ("date",)),
        ClaimFieldProjection("retail_order.total", "totals", "total", ("money",)),
    ),
    line_item_projection=ClaimLineItemProjection(
        canonical_prefix="retail_order.line_item.",
        field_map={
            "description": "description",
            "quantity": "quantity",
            "unit_price": "unit_price",
            "amount": "amount",
        },
        value_types={
            "description": ("text",),
            "quantity": ("number", "quantity"),
            "unit_price": ("money",),
            "amount": ("money",),
        },
    ),
)

CLAIM_FAMILY_REGISTRIES: dict[str, ClaimFamilyRegistry] = {
    registry.family: registry
    for registry in (
        INVOICE_CLAIM_REGISTRY,
        RECEIPT_CLAIM_REGISTRY,
        MEDICAL_EOB_CLAIM_REGISTRY,
        SERVICE_RECORD_CLAIM_REGISTRY,
        RETAIL_ORDER_CLAIM_REGISTRY,
    )
}


def claim_key_is_admissible(canonical_key: str) -> bool:
    family, separator, _field_name = canonical_key.partition(".")
    if not separator:
        return True
    registry = CLAIM_FAMILY_REGISTRIES.get(family)
    if registry is None:
        return True
    if any(projection.canonical_key == canonical_key for projection in registry.field_projections):
        return True
    if registry.line_item_projection is None:
        return False
    prefix = registry.line_item_projection.canonical_prefix
    if not canonical_key.startswith(prefix):
        return False
    suffix = canonical_key.removeprefix(prefix)
    return suffix in registry.line_item_projection.field_map


def claim_value_type_is_admissible(canonical_key: str, value_type: str) -> bool:
    family, separator, _field_name = canonical_key.partition(".")
    if not separator:
        return True
    registry = CLAIM_FAMILY_REGISTRIES.get(family)
    if registry is None:
        return True
    for projection in registry.field_projections:
        if projection.canonical_key == canonical_key:
            return value_type in projection.value_types
    if registry.line_item_projection is None:
        return False
    prefix = registry.line_item_projection.canonical_prefix
    if not canonical_key.startswith(prefix):
        return False
    suffix = canonical_key.removeprefix(prefix)
    value_types = registry.line_item_projection.value_types.get(suffix)
    return value_types is not None and value_type in value_types
