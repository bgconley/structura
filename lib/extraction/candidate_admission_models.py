from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from lib.extraction.contract_registry import CONTRACT_REGISTRY_VERSION
from lib.extraction.models import (
    CandidateFact,
    ExtractionRunScope,
    LineItemCandidateFact,
    ObservationCandidateFact,
)
from lib.model_runtime.reliability_versions import CANDIDATE_GATE_VERSION, PLANNER_VERSION
from lib.model_runtime.source_engines import is_model_source_engine

CandidateKind = Literal["field", "line_item", "observation"]


@dataclass(frozen=True)
class CandidateAdmissionContext:
    document_id: UUID
    run_scope: ExtractionRunScope
    source_engine: str
    model_output_schema_name: str | None
    run_id: str | None = None
    planner_version: str = PLANNER_VERSION
    candidate_gate_version: str = CANDIDATE_GATE_VERSION
    contract_registry_version: str = CONTRACT_REGISTRY_VERSION

    @property
    def plan_id(self) -> UUID | None:
        return self.run_scope.plan_id

    @property
    def plan_task_id(self) -> UUID | None:
        return self.run_scope.plan_task_id

    @property
    def semantic_annotation_id(self) -> UUID | None:
        return self.run_scope.semantic_annotation_id

    @property
    def semantic_region_id(self) -> UUID | None:
        return self.run_scope.source_semantic_region_id

    @property
    def semantic_type(self) -> str | None:
        return self.run_scope.semantic_type

    @property
    def region_envelope_version(self) -> str | None:
        return self.run_scope.region_envelope_version

    @property
    def model_backed_semantic_region(self) -> bool:
        return self.run_scope.extraction_scope == "semantic_region" and is_model_source_engine(
            self.source_engine
        )


@dataclass(frozen=True)
class CandidateAdmissionEvent:
    document_id: UUID
    plan_id: UUID | None
    plan_task_id: UUID | None
    semantic_annotation_id: UUID | None
    semantic_region_id: UUID | None
    run_id: str | None
    planner_version: str | None
    candidate_gate_version: str
    contract_registry_version: str
    region_envelope_version: str | None
    candidate_kind: CandidateKind
    candidate_fingerprint: str
    decision: str
    reasons: tuple[str, ...]
    field_path: str | None
    semantic_type: str | None
    model_output_schema_name: str | None
    source_engine: str
    evidence_concrete: bool
    payload_json: dict[str, Any]


@dataclass(frozen=True)
class CandidateAdmissionResult:
    field_candidates: list[CandidateFact]
    line_item_candidates: list[LineItemCandidateFact]
    observation_candidates: list[ObservationCandidateFact]
    events: list[CandidateAdmissionEvent]
    summary: dict[str, Any]
    rejected_candidates: list[dict[str, Any]]

    @property
    def candidate_count(self) -> int:
        return (
            len(self.field_candidates)
            + len(self.line_item_candidates)
            + len(self.observation_candidates)
        )
