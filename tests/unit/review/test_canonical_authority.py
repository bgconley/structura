from datetime import UTC, datetime
from uuid import uuid4

import pytest

from lib.extraction.canonical_authority import canonical_field_is_human_controlled
from lib.review.correction_revision import (
    CorrectionConflictError,
    CorrectionExpectation,
    assert_canonical_revision,
)


@pytest.mark.parametrize(
    "marker",
    [
        {"source_kind": "human"},
        {"review_status": "user_confirmed"},
        {"review_status": "user_corrected"},
        {"accepted_by_user_id": uuid4()},
    ],
)
def test_independent_human_markers_require_a_matching_revision(marker):
    current = datetime(2026, 9, 7, 18, 30, 0, 123456, tzinfo=UTC)
    row = {
        "source_kind": "candidate",
        "review_status": "auto_accepted",
        "accepted_by_user_id": None,
        "updated_at": current,
        **marker,
    }
    assert canonical_field_is_human_controlled(row)
    with pytest.raises(CorrectionConflictError):
        assert_canonical_revision(row, CorrectionExpectation())
    assert_canonical_revision(row, CorrectionExpectation(True, current.isoformat()))


@pytest.mark.parametrize("source_kind", ["candidate", "validator", "system"])
def test_machine_acceptance_is_not_human_authority(source_kind):
    row = {"source_kind": source_kind, "review_status": "auto_accepted"}
    assert not canonical_field_is_human_controlled(row)
    assert_canonical_revision(row, CorrectionExpectation())
