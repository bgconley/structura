from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Any

from lib.extraction.candidate_admission_events import (
    persist_candidate_admission_events as persist_candidate_admission_events,
)
from lib.extraction.candidate_admission_fingerprints import (
    field_fingerprint,
    line_item_fingerprint,
    observation_fingerprint,
    raw_payload_fingerprint,
)
from lib.extraction.candidate_admission_metadata import (
    with_candidate_admission_fingerprint,
    with_line_item_admission_fingerprint,
    with_observation_admission_fingerprint,
)
from lib.extraction.candidate_admission_models import (
    CANDIDATE_GATE_VERSION as CANDIDATE_GATE_VERSION,
)
from lib.extraction.candidate_admission_models import (
    CandidateAdmissionContext,
    CandidateAdmissionEvent,
    CandidateAdmissionResult,
    CandidateKind,
)
from lib.extraction.candidate_admission_payloads import (
    rejected_candidates_from_payload as rejected_candidates_from_payload,
)
from lib.extraction.candidate_admission_policy import decision_for_quality_reason
from lib.extraction.candidate_quality import (
    reject_line_item,
    reject_observation,
    reject_scalar_candidate,
)
from lib.extraction.candidate_schema_policy import (
    canonical_candidate_schema_rejection_reason,
    field_path_schema_rejection_reason,
)
from lib.extraction.evidence import has_concrete_evidence
from lib.extraction.models import (
    CandidateFact,
    LineItemCandidateFact,
    ObservationCandidateFact,
)


def admit_extraction_candidates(
    *,
    context: CandidateAdmissionContext,
    field_candidates: list[CandidateFact],
    line_item_candidates: list[LineItemCandidateFact],
    observation_candidates: list[ObservationCandidateFact],
    rejected_candidate_payloads: list[dict[str, Any]] | None = None,
) -> CandidateAdmissionResult:
    admitted_fields: list[CandidateFact] = []
    admitted_line_items: list[LineItemCandidateFact] = []
    admitted_observations: list[ObservationCandidateFact] = []
    events: list[CandidateAdmissionEvent] = []
    event_fingerprints: set[str] = set()
    admitted_fingerprints: set[str] = set()

    for field_candidate in field_candidates:
        event, admitted_field = _admit_field_candidate(
            context,
            field_candidate,
            admitted_fingerprints=admitted_fingerprints,
        )
        events.append(event)
        event_fingerprints.add(event.candidate_fingerprint)
        if admitted_field is not None:
            admitted_fields.append(admitted_field)
            admitted_fingerprints.add(event.candidate_fingerprint)

    for line_item_candidate in line_item_candidates:
        event, admitted_line_item = _admit_line_item_candidate(
            context,
            line_item_candidate,
            admitted_fingerprints=admitted_fingerprints,
        )
        events.append(event)
        event_fingerprints.add(event.candidate_fingerprint)
        if admitted_line_item is not None:
            admitted_line_items.append(admitted_line_item)
            admitted_fingerprints.add(event.candidate_fingerprint)

    for observation_candidate in observation_candidates:
        event, admitted_observation = _admit_observation_candidate(
            context,
            observation_candidate,
            admitted_fingerprints=admitted_fingerprints,
        )
        events.append(event)
        event_fingerprints.add(event.candidate_fingerprint)
        if admitted_observation is not None:
            admitted_observations.append(admitted_observation)
            admitted_fingerprints.add(event.candidate_fingerprint)

    for rejected in rejected_candidate_payloads or []:
        event = _rejected_payload_event(context, rejected)
        if event.candidate_fingerprint in event_fingerprints:
            continue
        events.append(event)
        event_fingerprints.add(event.candidate_fingerprint)

    rejected_candidates = [_rejected_summary(event) for event in events if _is_rejected(event)]
    return CandidateAdmissionResult(
        field_candidates=admitted_fields,
        line_item_candidates=admitted_line_items,
        observation_candidates=admitted_observations,
        events=events,
        summary=_admission_summary(events),
        rejected_candidates=rejected_candidates,
    )


def normalization_json_with_candidate_admission(
    normalization_json: dict[str, Any],
    admission: CandidateAdmissionResult,
) -> dict[str, Any]:
    updated = dict(normalization_json)
    updated["candidateAdmissionSummary"] = admission.summary
    updated["rejectedCandidates"] = list(admission.rejected_candidates)
    return updated


def _admit_field_candidate(
    context: CandidateAdmissionContext,
    candidate: CandidateFact,
    *,
    admitted_fingerprints: set[str],
) -> tuple[CandidateAdmissionEvent, CandidateFact | None]:
    payload = _field_payload(candidate)
    fingerprint = field_fingerprint(candidate, context)
    evidence_concrete = has_concrete_evidence(candidate.evidence)
    decision, reasons = _field_rejection_decision(context, candidate, evidence_concrete)
    if fingerprint in admitted_fingerprints:
        decision, reasons = "rejected_duplicate", ("duplicate_candidate_fingerprint",)
    if decision:
        return (
            _event(
                context,
                candidate_kind="field",
                candidate_fingerprint=fingerprint,
                decision=decision,
                reasons=reasons,
                field_path=candidate.field_path,
                evidence_concrete=evidence_concrete,
                payload_json=payload,
            ),
            None,
        )

    admitted = with_candidate_admission_fingerprint(
        _review_required_candidate(context, candidate), fingerprint
    )
    return (
        _event(
            context,
            candidate_kind="field",
            candidate_fingerprint=fingerprint,
            decision=_admitted_decision(admitted),
            reasons=(),
            field_path=admitted.field_path,
            evidence_concrete=evidence_concrete,
            payload_json=payload,
        ),
        admitted,
    )


def _admit_line_item_candidate(
    context: CandidateAdmissionContext,
    candidate: LineItemCandidateFact,
    *,
    admitted_fingerprints: set[str],
) -> tuple[CandidateAdmissionEvent, LineItemCandidateFact | None]:
    payload = _line_item_payload(candidate)
    fingerprint = line_item_fingerprint(candidate, context)
    evidence_concrete = has_concrete_evidence(candidate.evidence)
    decision, reasons = _line_item_rejection_decision(context, candidate, evidence_concrete)
    if fingerprint in admitted_fingerprints:
        decision, reasons = "rejected_duplicate", ("duplicate_candidate_fingerprint",)
    if decision:
        return (
            _event(
                context,
                candidate_kind="line_item",
                candidate_fingerprint=fingerprint,
                decision=decision,
                reasons=reasons,
                field_path=None,
                evidence_concrete=evidence_concrete,
                payload_json=payload,
            ),
            None,
        )

    admitted = with_line_item_admission_fingerprint(
        _review_required_line_item(context, candidate),
        fingerprint,
    )
    return (
        _event(
            context,
            candidate_kind="line_item",
            candidate_fingerprint=fingerprint,
            decision=_admitted_decision(admitted),
            reasons=(),
            field_path=None,
            evidence_concrete=evidence_concrete,
            payload_json=payload,
        ),
        admitted,
    )


def _admit_observation_candidate(
    context: CandidateAdmissionContext,
    candidate: ObservationCandidateFact,
    *,
    admitted_fingerprints: set[str],
) -> tuple[CandidateAdmissionEvent, ObservationCandidateFact | None]:
    payload = _observation_payload(candidate)
    fingerprint = observation_fingerprint(candidate, context)
    evidence_concrete = has_concrete_evidence(candidate.evidence)
    decision, reasons = _observation_rejection_decision(context, candidate, evidence_concrete)
    if fingerprint in admitted_fingerprints:
        decision, reasons = "rejected_duplicate", ("duplicate_candidate_fingerprint",)
    if decision:
        return (
            _event(
                context,
                candidate_kind="observation",
                candidate_fingerprint=fingerprint,
                decision=decision,
                reasons=reasons,
                field_path=candidate.field_name,
                evidence_concrete=evidence_concrete,
                payload_json=payload,
            ),
            None,
        )

    admitted = with_observation_admission_fingerprint(
        replace(candidate, status="needs_review"), fingerprint
    )
    return (
        _event(
            context,
            candidate_kind="observation",
            candidate_fingerprint=fingerprint,
            decision="admitted_review_required",
            reasons=(),
            field_path=admitted.field_name,
            evidence_concrete=evidence_concrete,
            payload_json=payload,
        ),
        admitted,
    )


def _field_rejection_decision(
    context: CandidateAdmissionContext,
    candidate: CandidateFact,
    evidence_concrete: bool,
) -> tuple[str | None, tuple[str, ...]]:
    schema_reason = field_path_schema_rejection_reason(context, candidate.field_path)
    if schema_reason:
        return "rejected_family_schema", (schema_reason,)
    rejected, reason = reject_scalar_candidate(candidate.value)
    if rejected:
        return decision_for_quality_reason(reason)
    if context.model_backed_semantic_region and not evidence_concrete:
        return "rejected_missing_evidence", ("missing_concrete_evidence",)
    return None, ()


def _line_item_rejection_decision(
    context: CandidateAdmissionContext,
    candidate: LineItemCandidateFact,
    evidence_concrete: bool,
) -> tuple[str | None, tuple[str, ...]]:
    schema_reason = canonical_candidate_schema_rejection_reason(context)
    if schema_reason:
        return "rejected_family_schema", (schema_reason,)
    rejected, reason = reject_line_item(_line_item_payload(candidate))
    if rejected:
        return decision_for_quality_reason(reason)
    if context.model_backed_semantic_region and not evidence_concrete:
        return "rejected_missing_evidence", ("missing_concrete_evidence",)
    return None, ()


def _observation_rejection_decision(
    context: CandidateAdmissionContext,
    candidate: ObservationCandidateFact,
    evidence_concrete: bool,
) -> tuple[str | None, tuple[str, ...]]:
    rejected, reason = reject_observation(candidate.field_name, candidate.value)
    if rejected:
        return decision_for_quality_reason(reason)
    if context.model_backed_semantic_region and not evidence_concrete:
        return "rejected_missing_evidence", ("missing_concrete_evidence",)
    return None, ()


def _review_required_candidate(
    context: CandidateAdmissionContext,
    candidate: CandidateFact,
) -> CandidateFact:
    if context.model_backed_semantic_region:
        return replace(candidate, status="needs_review")
    return candidate


def _review_required_line_item(
    context: CandidateAdmissionContext,
    candidate: LineItemCandidateFact,
) -> LineItemCandidateFact:
    if context.model_backed_semantic_region:
        return replace(candidate, status="needs_review")
    return candidate


def _admitted_decision(candidate: CandidateFact | LineItemCandidateFact) -> str:
    if candidate.status == "needs_review":
        return "admitted_review_required"
    return "admitted_auto_promotable"


def _rejected_payload_event(
    context: CandidateAdmissionContext,
    payload: dict[str, Any],
) -> CandidateAdmissionEvent:
    candidate_kind = _candidate_kind(payload.get("candidate_kind"))
    field_path = _optional_string(payload.get("field_path"))
    payload_json = _dict(payload.get("payload"))
    decision = str(payload.get("decision") or "rejected_value_sanity")
    reasons = tuple(str(reason) for reason in payload.get("reasons") or ())
    evidence_concrete = _bool_value(payload.get("evidence_concrete", False))
    fingerprint = raw_payload_fingerprint(
        candidate_kind=candidate_kind,
        field_path=field_path,
        payload=payload_json,
        context=context,
    )
    return _event(
        context,
        candidate_kind=candidate_kind,
        candidate_fingerprint=fingerprint,
        decision=decision,
        reasons=reasons,
        field_path=field_path,
        evidence_concrete=evidence_concrete,
        payload_json=payload_json,
    )


def _event(
    context: CandidateAdmissionContext,
    *,
    candidate_kind: CandidateKind,
    candidate_fingerprint: str,
    decision: str,
    reasons: tuple[str, ...],
    field_path: str | None,
    evidence_concrete: bool,
    payload_json: dict[str, Any],
) -> CandidateAdmissionEvent:
    return CandidateAdmissionEvent(
        document_id=context.document_id,
        plan_id=context.plan_id,
        plan_task_id=context.plan_task_id,
        semantic_annotation_id=context.semantic_annotation_id,
        semantic_region_id=context.semantic_region_id,
        run_id=context.run_id,
        planner_version=context.planner_version,
        candidate_gate_version=context.candidate_gate_version,
        contract_registry_version=context.contract_registry_version,
        region_envelope_version=context.region_envelope_version,
        candidate_kind=candidate_kind,
        candidate_fingerprint=candidate_fingerprint,
        decision=decision,
        reasons=reasons,
        field_path=field_path,
        semantic_type=context.semantic_type,
        model_output_schema_name=context.model_output_schema_name,
        source_engine=context.source_engine,
        evidence_concrete=evidence_concrete,
        payload_json=payload_json,
    )


def _field_payload(candidate: CandidateFact) -> dict[str, Any]:
    return {
        "field_path": candidate.field_path,
        "value_type": candidate.value_type,
        "value": candidate.value,
        "currency": candidate.currency,
        "confidence": candidate.confidence,
        "evidence": candidate.evidence,
        "status": candidate.status,
    }


def _line_item_payload(candidate: LineItemCandidateFact) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "line_item_type": candidate.line_item_type,
        "ordinal": candidate.ordinal,
        "description": candidate.description,
        "code": candidate.code,
        "code_system": candidate.code_system,
        "service_date": candidate.service_date,
        "quantity": candidate.quantity,
        "unit": candidate.unit,
        "unit_price": candidate.unit_price,
        "gross_amount": candidate.gross_amount,
        "discount_amount": candidate.discount_amount,
        "tax_amount": candidate.tax_amount,
        "net_amount": candidate.net_amount,
        "currency": candidate.currency,
        "category_hint": candidate.category_hint,
        "confidence": candidate.confidence,
        "evidence": candidate.evidence,
        "status": candidate.status,
    }
    if candidate.net_amount is not None:
        payload["amount"] = {"amount": candidate.net_amount, "currency": candidate.currency}
    return {key: value for key, value in payload.items() if value not in (None, "")}


def _observation_payload(candidate: ObservationCandidateFact) -> dict[str, Any]:
    return {
        "observation_family": candidate.observation_family,
        "field_name": candidate.field_name,
        "value_type": candidate.value_type,
        "value": candidate.value,
        "confidence": candidate.confidence,
        "evidence": candidate.evidence,
        "status": candidate.status,
        "metadata": candidate.metadata,
    }


def _admission_summary(events: list[CandidateAdmissionEvent]) -> dict[str, Any]:
    decisions = Counter(event.decision for event in events)
    rejected = {
        decision: count
        for decision, count in sorted(decisions.items())
        if decision.startswith("rejected_")
    }
    admitted_count = sum(
        count for decision, count in decisions.items() if decision.startswith("admitted_")
    )
    rejected_count = sum(rejected.values())
    return {
        "produced": admitted_count + rejected_count,
        "admitted": admitted_count,
        "rejected": rejected_count,
        "rejectionReasons": rejected,
    }


def _rejected_summary(event: CandidateAdmissionEvent) -> dict[str, Any]:
    return {
        "candidateKind": event.candidate_kind,
        "candidateFingerprint": event.candidate_fingerprint,
        "decision": event.decision,
        "reasons": list(event.reasons),
        "fieldPath": event.field_path,
        "semanticType": event.semantic_type,
        "modelOutputSchemaName": event.model_output_schema_name,
        "evidenceConcrete": event.evidence_concrete,
    }


def _is_rejected(event: CandidateAdmissionEvent) -> bool:
    return event.decision.startswith("rejected_")


def _candidate_kind(value: object) -> CandidateKind:
    if value == "line_item":
        return "line_item"
    if value == "observation":
        return "observation"
    return "field"


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_string(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)
