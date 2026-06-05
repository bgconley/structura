from __future__ import annotations

from lib.extraction.candidate_admission_models import CandidateAdmissionContext

_FIELD_PATH_PREFIXES_BY_SCHEMA = {
    "invoice": ("invoice.",),
    "receipt": ("receipt.",),
    "retail_order": ("retail_order.",),
    "service_record": ("service_record.",),
    "medical_eob": ("medical_eob.",),
    "healthcare_coverage_decision": ("medical_eob.", "healthcare_coverage_decision."),
}

_OBSERVATION_ONLY_CANONICAL_TARGET_SCHEMAS = frozenset(
    {
        "document_observation",
        "retail_order",
        "service_record",
    }
)


def canonical_candidate_schema_rejection_reason(
    context: CandidateAdmissionContext,
) -> str | None:
    schema = _canonical_target_schema(context)
    if schema == "document_observation":
        return "document_observation_is_review_only"
    if schema in _OBSERVATION_ONLY_CANONICAL_TARGET_SCHEMAS:
        return "alias_family_requires_observation_projection"
    return None


def field_path_schema_rejection_reason(
    context: CandidateAdmissionContext,
    field_path: str,
) -> str | None:
    review_only_reason = canonical_candidate_schema_rejection_reason(context)
    if review_only_reason:
        return review_only_reason

    schema = _canonical_target_schema(context)
    if not schema:
        return None
    prefixes = _FIELD_PATH_PREFIXES_BY_SCHEMA.get(schema)
    if prefixes is None:
        return None

    normalized_field_path = field_path.strip().lower()
    if normalized_field_path.startswith(prefixes):
        return None
    return "candidate_schema_incompatible"


def _canonical_target_schema(context: CandidateAdmissionContext) -> str | None:
    value = context.run_scope.canonical_target_schema
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None
