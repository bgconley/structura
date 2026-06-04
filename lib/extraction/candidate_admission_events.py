from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.extraction.candidate_admission_models import CandidateAdmissionEvent


def persist_candidate_admission_events(
    cur: Any,
    *,
    extraction_id: UUID,
    events: list[CandidateAdmissionEvent],
) -> None:
    for event in events:
        cur.execute(
            """
            INSERT INTO candidate_admission_events (
              document_id, extraction_id, plan_id, plan_task_id,
              semantic_annotation_id, semantic_region_id, run_id,
              planner_version, candidate_gate_version, contract_registry_version,
              region_envelope_version, candidate_kind, candidate_fingerprint,
              decision, reasons, field_path, semantic_type, model_output_schema_name,
              source_engine, evidence_concrete, payload_json
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              %s::text[], %s, %s, %s, %s, %s, %s::jsonb
            )
            """,
            (
                event.document_id,
                extraction_id,
                event.plan_id,
                event.plan_task_id,
                event.semantic_annotation_id,
                event.semantic_region_id,
                event.run_id,
                event.planner_version,
                event.candidate_gate_version,
                event.contract_registry_version,
                event.region_envelope_version,
                event.candidate_kind,
                event.candidate_fingerprint,
                event.decision,
                list(event.reasons),
                event.field_path,
                event.semantic_type,
                event.model_output_schema_name,
                event.source_engine,
                event.evidence_concrete,
                Jsonb(_json_safe(event.payload_json)),
            ),
        )


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(_json_safe(key)): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_safe(item) for item in value]
    return str(value)
