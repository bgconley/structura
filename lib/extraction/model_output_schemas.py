from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from lib.config import get_settings
from lib.semantic_annotations.models import SemanticExtractionTask


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
    if schema_name == "invoice" and semantic_task.semantic_type == "invoice_line_item_table":
        return load_model_output_schema("granite_invoice_line_items.v1")
    if (
        schema_name == "medical_eob"
        and semantic_task.semantic_type == "covered_services_line_item_table"
    ):
        return load_model_output_schema("granite_medical_service_lines.v1")
    if schema_name == "invoice" and semantic_task.semantic_type == "payment_summary":
        return load_model_output_schema("granite_payment_summary.v1")
    if semantic_task.granite_task in {"tables_json", "tables_html", "tables_otsl"}:
        if schema_name == "invoice" and semantic_task.semantic_type == "invoice_line_item_table":
            return load_model_output_schema("granite_invoice_line_items.v1")
        if (
            schema_name == "medical_eob"
            and semantic_task.semantic_type == "covered_services_line_item_table"
        ):
            return load_model_output_schema("granite_medical_service_lines.v1")
    if semantic_task.granite_task == "kvp":
        if schema_name == "invoice" and semantic_task.semantic_type == "payment_summary":
            return load_model_output_schema("granite_payment_summary.v1")
    return None


@lru_cache(maxsize=16)
def load_model_output_schema(name: str) -> ModelOutputSchema:
    root = Path(get_settings().contracts_dir) / "model_outputs"
    path = root / f"{name}.schema.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    version = name.rsplit(".", 1)[-1]
    return ModelOutputSchema(name=name, version=version, schema=payload)
