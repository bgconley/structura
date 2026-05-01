from __future__ import annotations

from dataclasses import dataclass

from lib.semantic_annotations.models import SemanticExtractionTask


@dataclass(frozen=True)
class GraniteTaskBudget:
    max_output_tokens: int
    timeout_seconds: int
    max_attempts: int


DEFAULT_GRANITE_BUDGET = GraniteTaskBudget(
    max_output_tokens=1024,
    timeout_seconds=60,
    max_attempts=2,
)

LINE_ITEM_TABLE_BUDGET = GraniteTaskBudget(
    max_output_tokens=2048,
    timeout_seconds=90,
    max_attempts=2,
)

SUMMARY_KVP_BUDGET = GraniteTaskBudget(
    max_output_tokens=768,
    timeout_seconds=60,
    max_attempts=2,
)

OBSERVATION_BUDGET = GraniteTaskBudget(
    max_output_tokens=768,
    timeout_seconds=45,
    max_attempts=2,
)

SCHEMA_BACKED_OBSERVATION_BUDGET = GraniteTaskBudget(
    max_output_tokens=2048,
    timeout_seconds=75,
    max_attempts=2,
)

LINE_ITEM_SEMANTIC_TYPES = frozenset(
    {
        "invoice_line_item_table",
        "receipt_line_item_table",
        "retail_order_line_item_table",
        "service_record_line_item_table",
        "covered_services_line_item_table",
        "dispute_transaction_table",
    }
)

OBSERVATION_SEMANTIC_TYPES = frozenset(
    {
        "seller_information_block",
        "escrow_summary",
        "mortgage_payment_summary",
        "dispute_reason_block",
        "generic_form_kvp",
        "unsupported_document_region",
        "document_observation",
    }
)

SCHEMA_BACKED_OBSERVATION_SEMANTIC_TYPES = frozenset(
    {
        "seller_information_block",
        "escrow_summary",
        "mortgage_payment_summary",
        "dispute_reason_block",
        "generic_form_kvp",
        "unsupported_document_region",
    }
)


def granite_budget_for_task(
    *,
    schema_name: str,
    semantic_task: SemanticExtractionTask | None,
) -> GraniteTaskBudget:
    if semantic_task is None:
        return DEFAULT_GRANITE_BUDGET
    if semantic_task.semantic_type in LINE_ITEM_SEMANTIC_TYPES:
        return LINE_ITEM_TABLE_BUDGET
    if semantic_task.semantic_type in SCHEMA_BACKED_OBSERVATION_SEMANTIC_TYPES:
        return SCHEMA_BACKED_OBSERVATION_BUDGET
    if (
        semantic_task.target_schema == "document_observation"
        or schema_name == "document_observation"
    ):
        return OBSERVATION_BUDGET
    if semantic_task.semantic_type in OBSERVATION_SEMANTIC_TYPES:
        return OBSERVATION_BUDGET
    if semantic_task.granite_task == "kvp":
        return SUMMARY_KVP_BUDGET
    return DEFAULT_GRANITE_BUDGET
