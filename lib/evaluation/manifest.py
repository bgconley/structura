"""Frozen evaluation membership and policy, separately pinned by the caller."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from lib.evaluation.identity import Digest, EvaluationModel, Label

MATCHING_POLICY: Literal["structura.parse_matching.v1"] = "structura.parse_matching.v1"


class CaseBinding(EvaluationModel):
    item_id: Label
    annotation_sha256: Digest
    capture_sha256: Digest
    original_sha256: Digest
    processing_run_id: UUID
    parse_generation_id: UUID
    configuration_sha256: Digest
    profile: Label
    served_model: Label
    source_engine: Label
    fixture_type: Literal["deterministic_fixture", "model_backed"]
    origin_group: Label
    template_group: Label


class ExposureRecord(EvaluationModel):
    item_id: Label
    purpose: Literal["annotation", "adjudication", "development", "prompt_tuning", "evaluation"]
    occurred_at: datetime
    actor_reference: Label


class EvaluationManifest(EvaluationModel):
    schema_version: Literal["structura.parse_evaluation.v1"] = "structura.parse_evaluation.v1"
    evaluation_id: UUID
    frozen_at: datetime
    split: Literal["development", "validation", "blind_holdout", "synthetic_regression"]
    split_revision: Label
    matching_policy: Literal["structura.parse_matching.v1"] = MATCHING_POLICY
    threshold_policy: Literal["not_ratified"] = "not_ratified"
    cases: tuple[CaseBinding, ...] = Field(min_length=1, max_length=1000)
    exposures: tuple[ExposureRecord, ...] = Field(max_length=10000)
    # Registry entries for groups already exposed outside the holdout. Completeness
    # of this declaration remains a governance concern, not a scorer proof.
    development_origin_groups: tuple[Label, ...]
    development_template_groups: tuple[Label, ...]

    @model_validator(mode="after")
    def validate_freeze(self) -> EvaluationManifest:
        ids = {case.item_id for case in self.cases}
        if len(ids) != len(self.cases):
            raise ValueError("Frozen manifest case IDs must be unique.")
        if self.frozen_at.utcoffset() is None:
            raise ValueError("Freeze timestamp requires timezone.")
        for exposure in self.exposures:
            if exposure.item_id not in ids or exposure.occurred_at.utcoffset() is None:
                raise ValueError("Exposure must reference a case and a timezone-aware timestamp.")
            if exposure.occurred_at > self.frozen_at:
                raise ValueError("Frozen exposure records cannot postdate the manifest.")
            if self.split == "blind_holdout" and exposure.purpose in {
                "development",
                "prompt_tuning",
                "evaluation",
            }:
                raise ValueError("Previously evaluated or tuned cases are not untouched holdout.")
        if self.split == "blind_holdout" and any(
            case.origin_group in self.development_origin_groups
            or case.template_group in self.development_template_groups
            for case in self.cases
        ):
            raise ValueError("Holdout origin/template groups overlap development.")
        return self
