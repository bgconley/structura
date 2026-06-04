from __future__ import annotations

from typing import Any
from uuid import uuid4

from lib.extraction.canonical_repository import promote_candidates
from lib.extraction.models import ExtractionSourceDocument, ValidationReport


def test_required_candidate_without_concrete_evidence_is_not_auto_promoted() -> None:
    cur = RecordingCursor(fetches=[None, {"id": uuid4()}])
    source = _source()
    candidate = {
        "id": uuid4(),
        "field_path": "invoice.invoice_number",
        "ordinal": 1,
        "value_type": "string",
        "text_value": "INV-1001",
        "integer_value": None,
        "numeric_value": None,
        "boolean_value": None,
        "date_value": None,
        "timestamp_value": None,
        "json_value": None,
        "currency_code": None,
        "confidence": 0.95,
        "evidence_json": [],
        "validation_json": {},
        "status": "proposed",
    }

    promoted = promote_candidates(
        cur,
        source=source,
        extraction_id=uuid4(),
        candidates=[candidate],
        validation=ValidationReport(needs_review=False, checks=[]),
        schema_name="invoice",
    )

    assert promoted == 0
    assert not any("INSERT INTO canonical_fields" in sql for sql, _params in cur.queries)


class RecordingCursor:
    def __init__(self, *, fetches: list[dict[str, Any] | None]) -> None:
        self.fetches = list(fetches)
        self.queries: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.queries.append((sql, params))

    def fetchone(self) -> dict[str, Any] | None:
        return self.fetches.pop(0) if self.fetches else None


def _source() -> ExtractionSourceDocument:
    return ExtractionSourceDocument(
        document_id=uuid4(),
        household_id=uuid4(),
        title="Invoice INV-1001",
        original_filename="invoice.pdf",
        mime_type="application/pdf",
        family="invoice",
        subtype=None,
        sensitivity="normal",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[],
        elements=[],
        tables=[],
    )
