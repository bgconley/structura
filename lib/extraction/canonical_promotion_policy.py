from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lib.extraction.evidence import has_concrete_evidence
from lib.model_runtime.source_engines import is_model_source_engine

REQUIRED_CANONICAL_FIELD_PATHS = frozenset(
    {
        "invoice.invoice_number",
        "invoice.issued_date",
        "invoice.issue_date",
        "invoice.total_amount",
        "medical_eob.claim_number",
        "medical_eob.patient_name",
        "receipt.receipt_date",
        "receipt.transaction.date_local",
        "receipt.total_amount",
        "receipt.transaction.total",
    }
)


def candidate_auto_promotion_rejection_reason(candidate: Mapping[str, Any]) -> str | None:
    if candidate.get("status") != "proposed":
        return "candidate_not_proposed"
    if is_model_source_engine(candidate.get("source_engine")):
        # Model self-reported confidence is uncalibrated and may not gate
        # promotion; model-backed values always route to human review.
        return "model_backed_value_requires_review"
    if _is_required_field(str(candidate.get("field_path") or "")) and not has_concrete_evidence(
        _evidence(candidate)
    ):
        return "required_field_missing_concrete_evidence"
    return None


def _is_required_field(field_path: str) -> bool:
    normalized = ".".join(part for part in field_path.strip().lower().split(".") if part)
    return normalized in REQUIRED_CANONICAL_FIELD_PATHS or normalized.endswith(
        (".invoice_number", ".total_amount")
    )


def _evidence(candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = candidate.get("evidence_json") or candidate.get("evidenceJson") or []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
