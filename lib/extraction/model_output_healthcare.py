from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from lib.extraction.evidence_context import EvidenceContext
from lib.extraction.model_output_observations import should_drop_observation

HEALTHCARE_COVERAGE_SCHEMA = "granite_healthcare_coverage_decision.v1"


def healthcare_coverage_decision_output(
    document_id: UUID,
    payload: dict[str, Any],
    *,
    evidence_context: EvidenceContext | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    deferred_observation_count = 0
    for item in payload.get("facts") or []:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        if not name or should_drop_observation(name, value):
            continue
        deferred_observation_count += 1

    for item in payload.get("contacts") or []:
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            if key in {"confidence", "source_text"} or should_drop_observation(key, value):
                continue
            deferred_observation_count += 1

    for item in payload.get("service_lines") or []:
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            if key in {"confidence", "source_text"} or should_drop_observation(key, value):
                continue
            deferred_observation_count += 1

    return (
        {
            "schema_name": "document_observation",
            "schema_version": "v1",
            "document_id": str(document_id),
            "observations": [],
            "confidence": (
                payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
            ),
            "created_at": datetime.now(UTC).isoformat(),
            "metadata": {
                "model_output_schema_name": HEALTHCARE_COVERAGE_SCHEMA,
                "deferred_observation_count": deferred_observation_count,
            },
        },
        {
            "mapper": HEALTHCARE_COVERAGE_SCHEMA,
            "repairs": ["deferred_unbounded_healthcare_coverage_decision_observations"],
            "deferred_observation_count": deferred_observation_count,
            "rejected_fields": _rejected_fields(
                payload,
                {"facts", "contacts", "service_lines", "warnings", "confidence"},
            ),
        },
    )


def _rejected_fields(payload: dict[str, Any], accepted: set[str]) -> list[str]:
    return sorted(key for key in payload if key not in accepted)
