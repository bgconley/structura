from __future__ import annotations

from lib.extraction.candidate_admission_models import CandidateAdmissionContext
from lib.extraction.evidence import has_concrete_evidence, has_structural_value_anchor
from lib.extraction.models import Evidence
from lib.model_runtime.source_engines import is_model_source_engine


def candidate_evidence_concrete(
    context: CandidateAdmissionContext,
    evidence: list[Evidence],
) -> bool:
    if is_model_source_engine(context.source_engine):
        return has_structural_value_anchor(evidence)
    return has_concrete_evidence(evidence)


def missing_evidence_reason(
    context: CandidateAdmissionContext,
    evidence: list[Evidence],
    *,
    evidence_concrete: bool,
) -> str | None:
    if evidence_concrete:
        return None
    if is_model_source_engine(context.source_engine) and has_concrete_evidence(evidence):
        return "missing_structural_value_anchor"
    return "missing_concrete_evidence"
