from __future__ import annotations

from lib.extraction.canonical_promotion_policy import (
    candidate_auto_promotion_rejection_reason,
)

_CONCRETE_EVIDENCE = [{"page_number": 1, "element_id": "el-1", "source_engine": "docling"}]


def test_deterministic_candidate_with_concrete_evidence_is_promotable() -> None:
    candidate = {
        "status": "proposed",
        "source_engine": "docling",
        "field_path": "invoice.invoice_number",
        "evidence_json": _CONCRETE_EVIDENCE,
    }
    assert candidate_auto_promotion_rejection_reason(candidate) is None


def test_model_backed_candidate_never_auto_promotes_regardless_of_confidence() -> None:
    candidate = {
        "status": "proposed",
        "source_engine": "granite_vision_3b",
        "confidence": 0.99,
        "field_path": "invoice.invoice_number",
        "evidence_json": _CONCRETE_EVIDENCE,
    }
    assert (
        candidate_auto_promotion_rejection_reason(candidate) == "model_backed_value_requires_review"
    )


def test_non_proposed_candidate_is_not_promotable() -> None:
    candidate = {
        "status": "needs_review",
        "source_engine": "docling",
        "field_path": "invoice.invoice_number",
        "evidence_json": _CONCRETE_EVIDENCE,
    }
    assert candidate_auto_promotion_rejection_reason(candidate) == "candidate_not_proposed"


def test_required_field_without_concrete_evidence_is_rejected() -> None:
    candidate = {
        "status": "proposed",
        "source_engine": "docling",
        "field_path": "invoice.total_amount",
        "evidence_json": [{"page_number": 1, "source_engine": "docling"}],
    }
    assert (
        candidate_auto_promotion_rejection_reason(candidate)
        == "required_field_missing_concrete_evidence"
    )
