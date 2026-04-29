from __future__ import annotations

from lib.extraction.extraction_repository import _status_for_persisted_extraction
from lib.extraction.models import ValidationReport


def test_schema_validation_review_does_not_mark_persisted_extraction_failed() -> None:
    validation = ValidationReport(
        needs_review=True,
        checks=[
            {
                "code": "json_schema",
                "status": "failed",
                "message": "Model output did not match the target schema.",
            }
        ],
    )

    assert _status_for_persisted_extraction(validation) == "completed"
