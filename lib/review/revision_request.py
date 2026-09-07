"""Preserve omission versus explicit-null revision inputs at the service boundary."""

from typing import TypedDict

from lib.contracts import CanonicalFieldWrite, ReviewActionRequest
from lib.fact_authority.models import RevisionExpectation
from lib.review.correction_revision import CorrectionExpectation


class FieldRevisionArguments(TypedDict):
    expectation: CorrectionExpectation
    decision_expectation: RevisionExpectation
    path_guard_expectation: RevisionExpectation


def field_revision_arguments(
    payload: CanonicalFieldWrite | ReviewActionRequest,
) -> FieldRevisionArguments:
    return {
        "expectation": CorrectionExpectation(
            "expected_updated_at" in payload.model_fields_set, payload.expected_updated_at
        ),
        "decision_expectation": RevisionExpectation(
            supplied="expected_decision_revision" in payload.model_fields_set,
            revision=payload.expected_decision_revision,
        ),
        "path_guard_expectation": RevisionExpectation(
            supplied="expected_path_guard_revision" in payload.model_fields_set,
            revision=payload.expected_path_guard_revision,
        ),
    }
