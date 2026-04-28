from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "contracts"
    / "schemas"
    / "semantic_annotation_manifest.v1.schema.json"
)


@lru_cache(maxsize=1)
def semantic_annotation_manifest_schema() -> dict[str, Any]:
    parsed = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise RuntimeError("Semantic annotation manifest schema must be a JSON object.")
    return parsed
