from uuid import uuid4

import pytest
from pydantic import ValidationError

from lib.contracts import CanonicalFieldWrite, ReviewActionRequest
from lib.review.revision_request import field_revision_arguments


def payload(**extra):
    return {
        "documentId": str(uuid4()),
        "actionType": "reject_field",
        "fieldPath": "invoice.purchase_order",
        **extra,
    }


def test_revision_input_retains_omission_explicit_absence_and_independent_current_identities():
    omitted = field_revision_arguments(ReviewActionRequest.model_validate(payload()))
    assert all(not value.supplied for value in omitted.values())
    absent = field_revision_arguments(
        ReviewActionRequest.model_validate(
            payload(
                expectedUpdatedAt=None,
                expectedDecisionRevision=None,
                expectedPathGuardRevision=None,
            )
        )
    )
    assert all(value.supplied for value in absent.values())
    assert absent["expectation"].updated_at is None
    decision, guard = uuid4(), uuid4()
    exact = field_revision_arguments(
        ReviewActionRequest.model_validate(
            payload(expectedDecisionRevision=str(decision), expectedPathGuardRevision=str(guard))
        )
    )
    assert exact["decision_expectation"].revision == decision
    assert exact["path_guard_expectation"].revision == guard
    assert not exact["expectation"].supplied


@pytest.mark.parametrize("name", ["expectedDecisionRevision", "expectedPathGuardRevision"])
def test_non_field_actions_cannot_silently_ignore_new_revision_preconditions(name):
    with pytest.raises(ValidationError, match="canonical field action"):
        ReviewActionRequest.model_validate(payload(actionType="mark_done", **{name: None}))


@pytest.mark.parametrize("field_path", ["", "  ", "\n\t"])
def test_empty_field_identity_is_rejected_at_public_request_boundary(field_path):
    with pytest.raises(ValidationError):
        ReviewActionRequest.model_validate(payload(fieldPath=field_path))
    with pytest.raises(ValidationError):
        CanonicalFieldWrite.model_validate(
            {
                "fieldPath": field_path,
                "valueType": "string",
                "value": "Source supported",
                "sourceKind": "human",
                "evidence": [
                    {"pageNumber": 1, "sourceText": "Source supported", "sourceEngine": "human"}
                ],
            }
        )
