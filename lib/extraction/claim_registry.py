from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClaimFieldProjection:
    canonical_key: str
    container: str
    field_name: str


@dataclass(frozen=True)
class ClaimLineItemProjection:
    canonical_prefix: str
    field_map: dict[str, str]


@dataclass(frozen=True)
class ClaimFamilyRegistry:
    family: str
    field_projections: tuple[ClaimFieldProjection, ...]
    line_item_projection: ClaimLineItemProjection | None = None
    required_keys: tuple[str, ...] = ()


INVOICE_CLAIM_REGISTRY = ClaimFamilyRegistry(
    family="invoice",
    field_projections=(
        ClaimFieldProjection("invoice.invoice_number", "invoice", "invoice_number"),
        ClaimFieldProjection("invoice.issue_date", "invoice", "issued_on"),
        ClaimFieldProjection("invoice.due_date", "invoice", "due_on"),
        ClaimFieldProjection("invoice.subtotal", "totals", "subtotal"),
        ClaimFieldProjection("invoice.tax_total", "totals", "tax_total"),
        ClaimFieldProjection("invoice.total_amount", "totals", "total"),
        ClaimFieldProjection("invoice.balance_due", "totals", "balance_due"),
        ClaimFieldProjection("invoice.amount_paid", "totals", "amount_paid"),
    ),
    required_keys=("invoice.invoice_number", "invoice.total_amount"),
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
    ),
)

RECEIPT_CLAIM_REGISTRY = ClaimFamilyRegistry(
    family="receipt",
    field_projections=(
        ClaimFieldProjection("receipt.merchant.display_name", "merchant", "display_name"),
        ClaimFieldProjection("receipt.transaction.date_local", "transaction", "date_local"),
        ClaimFieldProjection("receipt.transaction.subtotal", "transaction", "subtotal"),
        ClaimFieldProjection("receipt.transaction.tax", "transaction", "tax"),
        ClaimFieldProjection("receipt.transaction.tip", "transaction", "tip"),
        ClaimFieldProjection("receipt.transaction.total", "transaction", "total"),
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
    ),
)

MEDICAL_EOB_CLAIM_REGISTRY = ClaimFamilyRegistry(
    family="medical_eob",
    field_projections=(
        ClaimFieldProjection("medical_eob.payer.display_name", "payer", "display_name"),
        ClaimFieldProjection("medical_eob.patient.display_name", "patient", "display_name"),
        ClaimFieldProjection("medical_eob.provider.display_name", "provider", "display_name"),
        ClaimFieldProjection("medical_eob.claim_number", "claim", "claim_number"),
        ClaimFieldProjection("medical_eob.received_on", "claim", "received_on"),
        ClaimFieldProjection("medical_eob.processed_on", "claim", "processed_on"),
        ClaimFieldProjection("medical_eob.group_number", "claim", "group_number"),
        ClaimFieldProjection("medical_eob.member_id", "claim", "member_id"),
        ClaimFieldProjection(
            "medical_eob.total_billed",
            "financial_summary",
            "total_billed",
        ),
        ClaimFieldProjection(
            "medical_eob.total_allowed",
            "financial_summary",
            "total_allowed",
        ),
        ClaimFieldProjection(
            "medical_eob.total_plan_paid",
            "financial_summary",
            "total_plan_paid",
        ),
        ClaimFieldProjection(
            "medical_eob.total_patient_responsibility",
            "financial_summary",
            "total_patient_responsibility",
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
    ),
)

SERVICE_RECORD_CLAIM_REGISTRY = ClaimFamilyRegistry(
    family="service_record",
    field_projections=(
        ClaimFieldProjection("service_record.subtotal", "totals", "subtotal"),
        ClaimFieldProjection("service_record.tax", "totals", "tax"),
        ClaimFieldProjection("service_record.total", "totals", "total"),
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
    ),
)

RETAIL_ORDER_CLAIM_REGISTRY = ClaimFamilyRegistry(
    family="retail_order",
    field_projections=(
        ClaimFieldProjection("retail_order.merchant_name", "order", "merchant_name"),
        ClaimFieldProjection("retail_order.order_number", "order", "order_number"),
        ClaimFieldProjection("retail_order.order_date", "order", "order_date"),
        ClaimFieldProjection("retail_order.total", "totals", "total"),
    ),
    line_item_projection=ClaimLineItemProjection(
        canonical_prefix="retail_order.line_item.",
        field_map={
            "description": "description",
            "quantity": "quantity",
            "unit_price": "unit_price",
            "amount": "amount",
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
