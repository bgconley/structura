"""Optimistic concurrency policy for human canonical corrections."""

from dataclasses import dataclass
from datetime import datetime

from lib.review.correction_values import correction_storage_value


class CorrectionConflictError(Exception):
    """The editor's view of the accepted field is no longer current."""


@dataclass(frozen=True)
class CorrectionExpectation:
    supplied: bool = False
    updated_at: str | None = None


def assert_correction_revision(
    *,
    exists: bool,
    updated_at: datetime | None,
    human_reviewed: bool,
    expectation: CorrectionExpectation,
) -> None:
    if not expectation.supplied:
        # Legacy clients can create facts and make the first human decision on
        # machine output. They cannot silently replace any human-reviewed fact.
        if human_reviewed:
            raise CorrectionConflictError(
                "This field has a human decision. Reload it and include its current revision."
            )
        return
    expected = expectation.updated_at
    if expected is None:
        matches = not exists
    else:
        parsed = correction_storage_value("datetime", expected)
        matches = exists and parsed == updated_at
    if not matches:
        raise CorrectionConflictError(
            "This field changed since it was loaded. Reload it before saving your correction."
        )
