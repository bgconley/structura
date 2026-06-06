from __future__ import annotations

from typing import Any

from lib.extraction.candidate_admission_models import CandidateAdmissionContext, CandidateKind
from lib.extraction.candidate_admission_policy import decision_for_quality_reason
from lib.extraction.candidate_quality import (
    reject_line_item,
    reject_observation,
    reject_scalar_candidate,
)
from lib.extraction.evidence import has_concrete_evidence


def rejected_candidates_from_payload(
    *,
    schema_name: str,
    payload: dict[str, Any],
    context: CandidateAdmissionContext,
    require_concrete_evidence: bool,
) -> list[dict[str, Any]]:
    rejected: list[dict[str, Any]] = []
    rejected.extend(
        _field_rejections_from_payload(
            schema_name=schema_name,
            payload=payload,
            context=context,
            require_concrete_evidence=require_concrete_evidence,
        )
    )
    rejected.extend(
        _line_item_rejections_from_payload(
            schema_name=schema_name,
            payload=payload,
            require_concrete_evidence=require_concrete_evidence,
        )
    )
    rejected.extend(_table_consistency_rejections_from_payload(payload))
    rejected.extend(
        _observation_rejections_from_payload(
            schema_name=schema_name,
            payload=payload,
            require_concrete_evidence=require_concrete_evidence,
        )
    )
    return rejected


def _table_consistency_rejections_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = _dict(payload.get("metadata"))
    table_consistency = _dict(metadata.get("tableConsistency") or metadata.get("table_consistency"))
    rejected_rows = table_consistency.get("rejectedRows") or table_consistency.get("rejected_rows")
    if not isinstance(rejected_rows, list):
        return []

    rejected: list[dict[str, Any]] = []
    for item in rejected_rows:
        if not isinstance(item, dict):
            continue
        row_payload = _dict(item.get("payload"))
        if not row_payload:
            continue
        evidence = _evidence(row_payload)
        reason = str(item.get("reason") or "candidate.table_consistency_rejected")
        rejected.append(
            _raw_rejection_payload(
                candidate_kind="line_item",
                field_path=None,
                payload=row_payload,
                decision="rejected_table_consistency",
                reasons=(reason,),
                evidence_concrete=has_concrete_evidence(evidence),
            )
        )
    return rejected


def _field_rejections_from_payload(
    *,
    schema_name: str,
    payload: dict[str, Any],
    context: CandidateAdmissionContext,
    require_concrete_evidence: bool,
) -> list[dict[str, Any]]:
    rejected: list[dict[str, Any]] = []
    if context.run_scope.canonical_target_schema == "document_observation":
        return rejected
    for field_path, owner, value in _field_payload_values(schema_name, payload):
        if value in (None, ""):
            continue
        quality_rejected, quality_reason = reject_scalar_candidate(value)
        evidence = _evidence(owner)
        if quality_rejected:
            decision, reasons = decision_for_quality_reason(quality_reason)
        elif require_concrete_evidence and not has_concrete_evidence(evidence):
            decision, reasons = "rejected_missing_evidence", ("missing_concrete_evidence",)
        else:
            continue
        rejected.append(
            _raw_rejection_payload(
                candidate_kind="field",
                field_path=field_path,
                payload={"field_path": field_path, "value": value, "evidence": evidence},
                decision=decision,
                reasons=reasons,
                evidence_concrete=has_concrete_evidence(evidence),
            )
        )
    return rejected


def _line_item_rejections_from_payload(
    *,
    schema_name: str,
    payload: dict[str, Any],
    require_concrete_evidence: bool,
) -> list[dict[str, Any]]:
    rejected: list[dict[str, Any]] = []
    raw_items = (
        payload.get("service_lines") if schema_name == "medical_eob" else payload.get("line_items")
    )
    if not isinstance(raw_items, list):
        return rejected
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        quality_rejected, quality_reason = reject_line_item(item)
        evidence = _evidence(item)
        if quality_rejected:
            decision, reasons = decision_for_quality_reason(quality_reason)
        elif require_concrete_evidence and not has_concrete_evidence(evidence):
            decision, reasons = "rejected_missing_evidence", ("missing_concrete_evidence",)
        else:
            continue
        rejected.append(
            _raw_rejection_payload(
                candidate_kind="line_item",
                field_path=None,
                payload=item,
                decision=decision,
                reasons=reasons,
                evidence_concrete=has_concrete_evidence(evidence),
            )
        )
    return rejected


def _observation_rejections_from_payload(
    *,
    schema_name: str,
    payload: dict[str, Any],
    require_concrete_evidence: bool,
) -> list[dict[str, Any]]:
    if schema_name != "document_observation":
        return []
    raw_items = payload.get("observations")
    if not isinstance(raw_items, list):
        return []
    rejected: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        field_name = str(item.get("field_name") or "")
        value = item.get("value")
        quality_rejected, quality_reason = reject_observation(field_name, value)
        evidence = _evidence(item)
        if quality_rejected:
            decision, reasons = decision_for_quality_reason(quality_reason)
        elif require_concrete_evidence and not has_concrete_evidence(evidence):
            decision, reasons = "rejected_missing_evidence", ("missing_concrete_evidence",)
        else:
            continue
        rejected.append(
            _raw_rejection_payload(
                candidate_kind="observation",
                field_path=field_name or None,
                payload=item,
                decision=decision,
                reasons=reasons,
                evidence_concrete=has_concrete_evidence(evidence),
            )
        )
    return rejected


def _field_payload_values(
    schema_name: str,
    payload: dict[str, Any],
) -> list[tuple[str, dict[str, Any], Any]]:
    if schema_name == "receipt":
        merchant = _dict(payload.get("merchant"))
        transaction = _dict(payload.get("transaction"))
        return [
            ("receipt.merchant.display_name", merchant, merchant.get("display_name")),
            ("receipt.transaction.date_local", transaction, transaction.get("date_local")),
            (
                "receipt.transaction.subtotal",
                _dict(transaction.get("subtotal")),
                transaction.get("subtotal"),
            ),
            ("receipt.transaction.tax", _dict(transaction.get("tax")), transaction.get("tax")),
            (
                "receipt.transaction.total",
                _dict(transaction.get("total")),
                transaction.get("total"),
            ),
        ]
    if schema_name == "invoice":
        seller = _dict(payload.get("seller"))
        invoice = _dict(payload.get("invoice"))
        totals = _dict(payload.get("totals"))
        return [
            ("invoice.seller.display_name", seller, seller.get("display_name")),
            ("invoice.invoice_number", invoice, invoice.get("invoice_number")),
            ("invoice.issue_date", invoice, invoice.get("issued_on")),
            ("invoice.due_date", invoice, invoice.get("due_on")),
            ("invoice.subtotal", _dict(totals.get("subtotal")), totals.get("subtotal")),
            ("invoice.tax_total", _dict(totals.get("tax_total")), totals.get("tax_total")),
            (
                "invoice.shipping_total",
                _dict(totals.get("shipping_total")),
                totals.get("shipping_total"),
            ),
            (
                "invoice.discount_total",
                _dict(totals.get("discount_total")),
                totals.get("discount_total"),
            ),
            ("invoice.total_amount", _dict(totals.get("total")), totals.get("total")),
            ("invoice.balance_due", _dict(totals.get("balance_due")), totals.get("balance_due")),
        ]
    if schema_name == "medical_eob":
        payer = _dict(payload.get("payer"))
        patient = _dict(payload.get("patient"))
        provider = _dict(payload.get("provider"))
        claim = _dict(payload.get("claim"))
        summary = _dict(payload.get("financial_summary"))
        return [
            ("medical_eob.payer.display_name", payer, payer.get("display_name")),
            ("medical_eob.patient.display_name", patient, patient.get("display_name")),
            ("medical_eob.provider.display_name", provider, provider.get("display_name")),
            ("medical_eob.claim_number", claim, claim.get("claim_number")),
            (
                "medical_eob.total_billed",
                _dict(summary.get("total_billed")),
                summary.get("total_billed"),
            ),
            (
                "medical_eob.total_plan_paid",
                _dict(summary.get("total_plan_paid")),
                summary.get("total_plan_paid"),
            ),
            (
                "medical_eob.total_patient_responsibility",
                _dict(summary.get("total_patient_responsibility")),
                summary.get("total_patient_responsibility"),
            ),
        ]
    return []


def _raw_rejection_payload(
    *,
    candidate_kind: CandidateKind,
    field_path: str | None,
    payload: dict[str, Any],
    decision: str,
    reasons: tuple[str, ...],
    evidence_concrete: bool,
) -> dict[str, Any]:
    return {
        "candidate_kind": candidate_kind,
        "field_path": field_path,
        "payload": payload,
        "decision": decision,
        "reasons": list(reasons),
        "evidence_concrete": evidence_concrete,
    }


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _evidence(owner: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = owner.get("evidence")
    return evidence if isinstance(evidence, list) else []
