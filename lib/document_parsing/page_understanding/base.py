"""Immutable model-facing values; no application identities or trust fields."""

from pydantic import BaseModel, ConfigDict


class UnderstandingModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
