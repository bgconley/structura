from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from lib.extraction.evidence_context import EvidenceContext
from lib.extraction.model_output_observations import observation, should_drop_observation
from lib.extraction.model_output_value_parsing import number_value

HEALTHCARE_COVERAGE_SCHEMA = "granite_healthcare_coverage_decision.v1"


def healthcare_coverage_decision_output(
    document_id: UUID,
    payload: dict[str, Any],
    *,
    evidence_context: EvidenceContext | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for item in payload.get("facts") or []:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        if not name or should_drop_observation(name, value):
            continue
        observations.append(
            observation(
                field_name=str(name),
                value=value,
                family=HEALTHCARE_COVERAGE_SCHEMA,
                confidence=number_value(item.get("confidence")),
                source_text=item.get("source_text") or value,
                evidence_context=evidence_context,
            )
        )

    for index, item in enumerate(payload.get("contacts") or [], start=1):
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            if key in {"confidence", "source_text"} or should_drop_observation(key, value):
                continue
            observations.append(
                observation(
                    field_name=f"contact_{index}.{key}",
                    value=value,
                    family=HEALTHCARE_COVERAGE_SCHEMA,
                    confidence=number_value(item.get("confidence")),
                    source_text=item.get("source_text") or value,
                    evidence_context=evidence_context,
                )
            )

    for index, item in enumerate(payload.get("service_lines") or [], start=1):
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            if key in {"confidence", "source_text"} or should_drop_observation(key, value):
                continue
            observations.append(
                observation(
                    field_name=f"service_line_{index}.{key}",
                    value=value,
                    family=HEALTHCARE_COVERAGE_SCHEMA,
                    confidence=number_value(item.get("confidence")),
                    source_text=item.get("source_text") or value,
                    evidence_context=evidence_context,
                )
            )

    return (
        {
            "schema_name": "document_observation",
            "schema_version": "v1",
            "document_id": str(document_id),
            "observations": observations,
            "confidence": (
                payload.get("confidence") if isinstance(payload.get("confidence"), dict) else {}
            ),
            "created_at": datetime.now(UTC).isoformat(),
            "metadata": {"model_output_schema_name": HEALTHCARE_COVERAGE_SCHEMA},
        },
        {
            "mapper": HEALTHCARE_COVERAGE_SCHEMA,
            "repairs": ["mapped_healthcare_coverage_decision_to_observations"],
            "rejected_fields": _rejected_fields(
                payload,
                {"facts", "contacts", "service_lines", "warnings", "confidence"},
            ),
        },
    )


def _rejected_fields(payload: dict[str, Any], accepted: set[str]) -> list[str]:
    return sorted(key for key in payload if key not in accepted)
