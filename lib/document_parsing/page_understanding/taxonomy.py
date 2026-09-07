"""Frozen v2 page taxonomy; independent of legacy routing-profile vocabulary."""

from typing import Literal, get_args

Family = Literal[
    "receipt",
    "retail_order",
    "service_record",
    "invoice",
    "medical_eob",
    "medical_bill",
    "insurance_document",
    "insurance_denial",
    "real_estate_title",
    "mortgage_escrow_statement",
    "financial_dispute_form",
    "legal_contract",
    "legal_notice",
    "tax_document",
    "bank_statement",
    "financial_statement",
    "identity_document",
    "warranty",
    "handwritten_note",
    "typed_note",
    "whitepaper",
    "reference_document",
    "generic",
]
TypedFamily = Literal["receipt", "invoice", "medical_eob"]
FAMILIES: tuple[str, ...] = get_args(Family)
TYPED_FAMILIES: tuple[str, ...] = get_args(TypedFamily)
TAXONOMY_VERSION = "page-family-taxonomy-v2"
