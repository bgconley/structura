"""Exact source snapshots and public evidence projection, without storage paths."""

import json
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from lib.contracts.line_item_authority import (
    LineEvidenceRef,
    LineValidationCheck,
    LineValidationSummary,
)
from lib.fact_authority.projection_values import json_scalar, snapshot_digest

VALUE_COLUMNS = (
    "code",
    "code_system",
    "service_date",
    "description",
    "quantity",
    "unit",
    "unit_price",
    "gross_amount",
    "discount_amount",
    "tax_amount",
    "net_amount",
    "allowed_amount",
    "plan_paid_amount",
    "currency_code",
    "category_hint",
)
SOURCE_COLUMNS = (
    "id",
    "document_id",
    "extraction_id",
    "source_engine",
    "line_item_type",
    "candidate_group",
    "ordinal",
    *VALUE_COLUMNS,
)
EXTRACTION_COLUMNS = (
    "id",
    "document_id",
    "schema_name",
    "schema_version",
    "source_engine",
    "model_name",
    "model_version",
    "prompt_version",
    "extraction_scope",
    "semantic_annotation_id",
    "source_semantic_region_id",
)
_EVIDENCE_KEYS = {
    "pageNumber": "page_number",
    "sourceEngine": "source_engine",
    "bbox": "bbox",
    "elementId": "element_id",
    "tableId": "table_id",
    "rowIndex": "row_index",
    "columnIndex": "column_index",
    "sourceText": "source_text",
    "textSpan": "text_span",
    "confidence": "confidence",
}


def public_evidence(raw: object) -> tuple[list[LineEvidenceRef], bool]:
    if not isinstance(raw, list) or not raw:
        return [], False
    result: list[LineEvidenceRef] = []
    complete = True
    for item in raw:
        if not isinstance(item, Mapping):
            complete = False
            continue
        projected = {
            public: item.get(public, item.get(stored))
            for public, stored in _EVIDENCE_KEYS.items()
            if public in item or stored in item
        }
        try:
            result.append(LineEvidenceRef.model_validate(projected))
        except (ValidationError, ValueError, TypeError):
            complete = False
    return result, complete


def exact_json(value: object) -> Any:
    return json.loads(json.dumps(value, default=json_scalar, allow_nan=False))


def validation_summary(raw: object) -> LineValidationSummary:
    value = raw if isinstance(raw, dict) else {}
    raw_checks = value.get("checks")
    checks = []
    omitted = 0
    for item in raw_checks if isinstance(raw_checks, list) else []:
        try:
            if not isinstance(item, dict):
                raise ValueError()
            checks.append(
                LineValidationCheck.model_validate(
                    {"code": item.get("code"), "status": item.get("status")}
                )
            )
        except (ValueError, ValidationError):
            omitted += 1
    needs_review = value.get("needs_review", value.get("needsReview"))
    return LineValidationSummary(
        recorded=bool(value),
        needsReview=needs_review if type(needs_review) is bool else None,
        checks=checks,
        unrepresentedCheckCount=omitted,
    )


def source_snapshot(
    row: Mapping[str, Any],
    extraction: Mapping[str, Any] | None,
    original: Mapping[str, Any] | None,
    evidence: list[LineEvidenceRef],
) -> tuple[dict[str, Any], str]:
    snapshot = exact_json(
        {
            "schemaVersion": "line_item_source.v1",
            "candidate": {key: row.get(key) for key in SOURCE_COLUMNS},
            "extraction": {key: extraction.get(key) for key in EXTRACTION_COLUMNS}
            if extraction
            else None,
            "original": dict(original) if original else None,
            "evidence": [ref.model_dump(mode="json", by_alias=True) for ref in evidence],
            # Bind all stored validation and extended evidence without exposing raw
            # provider payloads, private URIs, or internal metadata in public snapshots.
            "validationSha256": snapshot_digest(row.get("validation_json")),
            "storedEvidenceSha256": snapshot_digest(row.get("evidence_json")),
        }
    )
    return snapshot, snapshot_digest(snapshot)
