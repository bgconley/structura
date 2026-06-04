from __future__ import annotations

from typing import Any

MODEL_SOURCE_ENGINES = frozenset(
    {
        "granite",
        "granite_vision",
        "granite_vision_3b",
        "model",
        "model_runtime",
        "qwen",
        "qwen_vl",
        "qwen3_vl_2b",
        "qwen3_vl_4b",
        "qwen3_vl_8b",
    }
)
MODEL_SOURCE_ENGINE_PREFIXES = ("granite_vision_", "qwen3_vl_")
NON_MODEL_SOURCE_ENGINES = frozenset(
    {
        "",
        "deterministic",
        "docling",
        "docling_text",
        "fixture",
        "heuristic",
        "human",
        "system",
        "system_reconciler",
        "validator",
    }
)


def normalize_source_engine(source_engine: Any) -> str:
    return str(source_engine or "").strip().lower()


def is_model_source_engine(source_engine: Any) -> bool:
    normalized = normalize_source_engine(source_engine)
    if normalized in NON_MODEL_SOURCE_ENGINES:
        return False
    return normalized in MODEL_SOURCE_ENGINES or normalized.startswith(MODEL_SOURCE_ENGINE_PREFIXES)


def is_non_model_source_engine(source_engine: Any) -> bool:
    return normalize_source_engine(source_engine) in NON_MODEL_SOURCE_ENGINES
