from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidatedModelOutputPayload:
    payload: dict[str, object]
    normalization: dict[str, object]
