"""Translate immutable authority state to the public canonical review contract."""

from lib.contracts.models import FieldDecision as DecisionResponse
from lib.contracts.models import FieldProjectionRevision
from lib.fact_authority.models import FieldDecision, ProjectionRevision


def decision_response(decision: FieldDecision) -> DecisionResponse:
    value = decision.model_dump(exclude={"field"})
    value.update(decision.field.model_dump())
    return DecisionResponse.model_validate(value)


def projection_response(projection: ProjectionRevision) -> FieldProjectionRevision:
    return FieldProjectionRevision.model_validate(projection.model_dump())
