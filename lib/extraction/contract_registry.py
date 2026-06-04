from __future__ import annotations

from dataclasses import dataclass

from lib.model_runtime.reliability_versions import (
    CONTRACT_REGISTRY_VERSION as CONTRACT_REGISTRY_VERSION,
)


@dataclass(frozen=True)
class ContractResolution:
    schema_name: str | None
    exact: bool
    review_only: bool
    reason: str
    compatibility_mode: str | None
    canonical_target_schema: str | None


_EXACT_CONTRACTS: dict[tuple[str, str, str, str], str] = {
    ("invoice", "invoice_line_item_table", "tables_json", "invoice"): (
        "granite_invoice_line_items.v1"
    ),
    ("invoice", "billing_summary", "kvp", "invoice"): "granite_payment_summary.v1",
    ("invoice", "payment_summary", "kvp", "invoice"): "granite_payment_summary.v1",
    ("receipt", "receipt_line_item_table", "tables_json", "receipt"): (
        "granite_receipt_line_items.v1"
    ),
    ("receipt", "receipt_payment_summary", "kvp", "receipt"): (
        "granite_receipt_payment_summary.v1"
    ),
    ("receipt", "payment_summary", "kvp", "receipt"): ("granite_receipt_payment_summary.v1"),
    ("service_record", "service_record_line_item_table", "tables_json", "receipt"): (
        "granite_service_record_line_items.v1"
    ),
    ("medical_eob", "covered_services_line_item_table", "tables_json", "medical_eob"): (
        "granite_medical_service_lines.v1"
    ),
    ("medical_eob", "patient_responsibility_summary", "kvp", "medical_eob"): (
        "granite_healthcare_coverage_decision.v1"
    ),
    ("medical_eob", "denial_or_coverage_decision", "kvp", "medical_eob"): (
        "granite_healthcare_coverage_decision.v1"
    ),
    (
        "healthcare_coverage_decision",
        "denial_or_coverage_decision",
        "kvp",
        "medical_eob",
    ): "granite_healthcare_coverage_decision.v1",
    (
        "real_estate_title",
        "seller_information_block",
        "kvp",
        "document_observation",
    ): "granite_real_estate_title_seller_info.v1",
    (
        "mortgage_escrow_statement",
        "escrow_summary",
        "kvp",
        "document_observation",
    ): "granite_mortgage_escrow_statement.v1",
    (
        "mortgage_escrow_statement",
        "mortgage_payment_summary",
        "kvp",
        "document_observation",
    ): "granite_mortgage_escrow_statement.v1",
    (
        "financial_dispute_form",
        "dispute_reason_block",
        "kvp",
        "document_observation",
    ): "granite_dispute_form.v1",
    (
        "financial_dispute_form",
        "dispute_transaction_table",
        "tables_json",
        "document_observation",
    ): "granite_dispute_form.v1",
    ("generic", "generic_form_kvp", "kvp", "document_observation"): ("granite_generic_kvp.v1"),
    ("generic_form", "generic_form_kvp", "kvp", "document_observation"): ("granite_generic_kvp.v1"),
    ("unsupported_document", "unsupported_document_region", "kvp", "document_observation"): (
        "granite_generic_kvp.v1"
    ),
}

_ALIAS_CONTRACTS: dict[tuple[str, str, str, str], str] = {
    ("retail_order", "retail_order_line_item_table", "tables_json", "receipt"): (
        "granite_retail_order.v1"
    ),
    ("retail_order", "receipt_line_item_table", "tables_json", "receipt"): (
        "granite_receipt_line_items.v1"
    ),
    ("service_record", "receipt_payment_summary", "kvp", "receipt"): (
        "granite_receipt_payment_summary.v1"
    ),
}

_GENERIC_REVIEW_ONLY_CONTRACTS: dict[tuple[str, str], str] = {
    ("generic_form_kvp", "kvp"): "granite_generic_kvp.v1",
    ("generic_form_kvp", "tables_json"): "granite_generic_kvp.v1",
    ("unsupported_document_region", "kvp"): "granite_generic_kvp.v1",
    ("document_header", "kvp"): "granite_generic_kvp.v1",
    ("document_footer", "kvp"): "granite_generic_kvp.v1",
    ("invoice_line_item_table", "tables_json"): "granite_generic_kvp.v1",
    ("receipt_line_item_table", "tables_json"): "granite_generic_kvp.v1",
    ("retail_order_line_item_table", "tables_json"): "granite_generic_kvp.v1",
    ("service_record_line_item_table", "tables_json"): "granite_generic_kvp.v1",
    ("covered_services_line_item_table", "tables_json"): "granite_generic_kvp.v1",
    ("dispute_transaction_table", "tables_json"): "granite_dispute_form.v1",
    ("receipt_payment_summary", "kvp"): "granite_generic_kvp.v1",
    ("payment_summary", "kvp"): "granite_generic_kvp.v1",
}

_COMPATIBLE_TARGETS = {
    "invoice": {"invoice", "document_observation"},
    "receipt": {"receipt", "document_observation"},
    "retail_order": {"receipt", "document_observation"},
    "service_record": {"receipt", "document_observation"},
    "medical_eob": {"medical_eob", "document_observation"},
    "healthcare_coverage_decision": {"medical_eob", "document_observation"},
    "real_estate_title": {"document_observation"},
    "mortgage_escrow_statement": {"document_observation"},
    "financial_dispute_form": {"document_observation"},
    "unsupported_document": set(),
    "generic_form": {"document_observation"},
    "generic": {"document_observation"},
}


def resolve_model_output_contract(
    *,
    resolved_document_type: str | None,
    semantic_type: str,
    granite_task: str,
    target_schema: str,
    allow_generic_fallback: bool,
) -> ContractResolution:
    document_type = _normalized(resolved_document_type) or _document_type_from_semantic_type(
        semantic_type,
        target_schema,
    )
    canonical_target_schema = canonical_target_schema_for(
        resolved_document_type=document_type,
        target_schema=target_schema,
    )
    if not schema_compatible(
        document_type=document_type,
        target_schema=target_schema,
    ):
        return ContractResolution(
            schema_name=None,
            exact=False,
            review_only=True,
            reason="family_schema_incompatible",
            compatibility_mode="missing",
            canonical_target_schema=canonical_target_schema,
        )

    key = (document_type, semantic_type, granite_task, target_schema)
    exact = _EXACT_CONTRACTS.get(key)
    if exact:
        return ContractResolution(
            schema_name=exact,
            exact=True,
            review_only=target_schema == "document_observation",
            reason="exact_contract",
            compatibility_mode="exact",
            canonical_target_schema=canonical_target_schema,
        )

    alias = _ALIAS_CONTRACTS.get(key)
    if alias:
        return ContractResolution(
            schema_name=alias,
            exact=False,
            review_only=target_schema == "document_observation",
            reason="compatible_alias_contract",
            compatibility_mode="compatible_alias",
            canonical_target_schema=canonical_target_schema,
        )

    if allow_generic_fallback and target_schema == "document_observation":
        fallback = _GENERIC_REVIEW_ONLY_CONTRACTS.get((semantic_type, granite_task))
        if fallback:
            return ContractResolution(
                schema_name=fallback,
                exact=False,
                review_only=True,
                reason="generic_review_only_fallback",
                compatibility_mode="generic_review_only",
                canonical_target_schema="document_observation",
            )

    return ContractResolution(
        schema_name=None,
        exact=False,
        review_only=True,
        reason="missing_contract",
        compatibility_mode="missing",
        canonical_target_schema=canonical_target_schema,
    )


def schema_compatible(*, document_type: str | None, target_schema: str) -> bool:
    if document_type is None:
        return True
    allowed = _COMPATIBLE_TARGETS.get(
        document_type,
        {document_type, "document_observation"},
    )
    return target_schema in allowed


def canonical_target_schema_for(
    *,
    resolved_document_type: str | None,
    target_schema: str,
) -> str:
    document_type = _normalized(resolved_document_type)
    if target_schema == "document_observation":
        return "document_observation"
    if document_type in {
        "retail_order",
        "service_record",
        "healthcare_coverage_decision",
        "real_estate_title",
        "mortgage_escrow_statement",
        "financial_dispute_form",
    }:
        return document_type
    return target_schema


def resolved_document_type_from_task_metadata(
    *,
    metadata: dict[str, object],
    semantic_type: str,
    target_schema: str,
) -> str:
    for key in ("resolved_document_type", "semantic_document_type"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return _document_type_from_semantic_type(semantic_type, target_schema)


def _document_type_from_semantic_type(semantic_type: str, target_schema: str) -> str:
    normalized = semantic_type.strip().lower()
    if normalized.startswith("service_record_"):
        return "service_record"
    if normalized.startswith("retail_order_"):
        return "retail_order"
    if normalized.startswith("receipt_"):
        return "receipt"
    if normalized.startswith("invoice_"):
        return "invoice"
    if normalized == "payment_summary":
        return target_schema
    if normalized in {"covered_services_line_item_table"}:
        return "medical_eob"
    if normalized == "denial_or_coverage_decision":
        return "healthcare_coverage_decision"
    if normalized == "seller_information_block":
        return "real_estate_title"
    if normalized in {"escrow_summary", "mortgage_payment_summary"}:
        return "mortgage_escrow_statement"
    if normalized in {"dispute_reason_block", "dispute_transaction_table"}:
        return "financial_dispute_form"
    if target_schema == "document_observation":
        return "generic"
    return target_schema


def _normalized(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None
