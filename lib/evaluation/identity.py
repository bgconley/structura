"""Canonical artifact identities; hashes establish consistency, not authenticity."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Label = Annotated[str, Field(min_length=1, max_length=200)]


class EvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


def artifact_digest(value: BaseModel | Any) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode()).hexdigest()
