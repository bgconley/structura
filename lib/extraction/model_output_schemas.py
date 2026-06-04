from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from lib.config import get_settings
from lib.extraction.contract_registry import (
    resolve_model_output_contract,
    resolved_document_type_from_task_metadata,
)
from lib.semantic_annotations.models import SemanticExtractionTask
from lib.semantic_annotations.task_routing import corrected_granite_task_for_semantic_type


@dataclass(frozen=True)
class ModelOutputSchema:
    name: str
    version: str
    schema: dict[str, Any]


def model_output_schema_for_task(
    *,
    schema_name: str,
    semantic_task: SemanticExtractionTask | None,
) -> ModelOutputSchema | None:
    if semantic_task is None:
        return None
    resolved_document_type = resolved_document_type_from_task_metadata(
        metadata=semantic_task.metadata,
        semantic_type=semantic_task.semantic_type,
        target_schema=schema_name,
    )
    resolution = resolve_model_output_contract(
        resolved_document_type=resolved_document_type,
        semantic_type=semantic_task.semantic_type,
        granite_task=_contract_granite_task(semantic_task),
        target_schema=schema_name,
        allow_generic_fallback=schema_name == "document_observation",
    )
    if resolution.schema_name is None:
        return None
    return load_model_output_schema(resolution.schema_name)


def _contract_granite_task(semantic_task: SemanticExtractionTask) -> str:
    granite_task, _repair = corrected_granite_task_for_semantic_type(
        semantic_type=semantic_task.semantic_type,
        granite_task=semantic_task.granite_task,
    )
    return granite_task or semantic_task.granite_task


@lru_cache(maxsize=16)
def load_model_output_schema(name: str) -> ModelOutputSchema:
    root = Path(get_settings().contracts_dir) / "model_outputs"
    path = root / f"{name}.schema.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    version = name.rsplit(".", 1)[-1]
    return ModelOutputSchema(name=name, version=version, schema=payload)
