from datetime import UTC, datetime

import pytest

from lib.extraction.candidate_repository import typed_value_columns, value_from_candidate_row
from lib.review.correction_revision import (
    CorrectionConflictError,
    CorrectionExpectation,
    assert_correction_revision,
)
from lib.review.correction_values import correction_storage_value


@pytest.mark.parametrize(
    ("value_type", "value", "column", "expected"),
    [
        ("date", "2024-02-29", "date_value", "2024-02-29"),
        (
            "datetime",
            "2026-09-07T14:30:00.123456-04:00",
            "timestamp_value",
            "2026-09-07T14:30:00.123456-04:00",
        ),
        (
            "json",
            {"paid": False, "items": [0, None]},
            "json_value",
            {"paid": False, "items": [0, None]},
        ),
    ],
)
def test_correction_round_trip_uses_the_typed_column(value_type, value, column, expected):
    columns = typed_value_columns(value_type, correction_storage_value(value_type, value))
    assert columns[column] is not None
    assert value_from_candidate_row({"value_type": value_type, **columns}) == expected
    assert columns["text_value"] is None


def test_legacy_datetime_text_remains_readable():
    assert (
        value_from_candidate_row({"value_type": "datetime", "text_value": "legacy value"})
        == "legacy value"
    )


def test_timestamp_revision_preserves_microseconds_and_offset_equivalence():
    current = datetime(2026, 9, 7, 18, 30, 0, 123456, tzinfo=UTC)
    assert_correction_revision(
        exists=True,
        updated_at=current,
        human_reviewed=True,
        expectation=CorrectionExpectation(True, "2026-09-07T14:30:00.123456-04:00"),
    )
    with pytest.raises(CorrectionConflictError):
        assert_correction_revision(
            exists=True,
            updated_at=current,
            human_reviewed=True,
            expectation=CorrectionExpectation(True, "2026-09-07T18:30:00.123Z"),
        )


@pytest.mark.parametrize("expectation", [CorrectionExpectation(), CorrectionExpectation(True)])
def test_legacy_or_create_only_request_cannot_overwrite_a_human_decision(expectation):
    with pytest.raises(CorrectionConflictError):
        assert_correction_revision(
            exists=True, updated_at=datetime.now(UTC), human_reviewed=True, expectation=expectation
        )


def test_missing_revision_allows_legacy_first_write_only():
    assert_correction_revision(
        exists=False, updated_at=None, human_reviewed=False, expectation=CorrectionExpectation()
    )
    assert_correction_revision(
        exists=True,
        updated_at=datetime.now(UTC),
        human_reviewed=False,
        expectation=CorrectionExpectation(),
    )
