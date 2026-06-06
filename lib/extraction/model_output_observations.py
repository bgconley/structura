from __future__ import annotations

from typing import Any

from lib.extraction.evidence_concretizer import evidence_ref_from_context
from lib.extraction.evidence_context import EvidenceContext
from lib.extraction.model_output_schemas import load_model_output_schema
from lib.extraction.model_output_value_parsing import (
    bounded_text,
    number_value,
    value_type,
)

DIRECT_OBSERVATION_METADATA_KEYS = frozenset({"confidence"})
DROP_FLAT_OBSERVATION_KEYS = {
    "$schema",
    "$defs",
    "type",
    "properties",
    "required",
    "additionalproperties",
    "items",
    "title",
    "description",
    "schema_name",
    "schema_version",
    "document_id",
    "created_at",
    "metadata",
    "validation",
    "confidence",
    "prompt",
    "instructions",
}
ECHO_PHRASES = (
    "return only",
    "json schema",
    "matching this schema",
    "do not copy these instructions",
    "semantic task from qwen",
    "<tables_json>",
    "additionalproperties",
)
GENERIC_KVP_SCHEMA_NAME = "granite_generic_kvp.v1"


def looks_like_schema_echo(payload: dict[str, Any]) -> bool:
    if "$schema" in payload or "$defs" in payload:
        return True
    if "properties" in payload and ("type" in payload or "required" in payload):
        schema_keys = {
            "$schema",
            "$defs",
            "type",
            "properties",
            "required",
            "additionalProperties",
            "title",
            "description",
            "items",
        }
        return set(payload).issubset(schema_keys)
    return False


def observations_from_model_payload(
    payload: dict[str, Any],
    model_output_schema_name: str | None,
    *,
    evidence_context: EvidenceContext | None,
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    fields = payload.get("fields")
    if isinstance(fields, list):
        if model_output_schema_name != GENERIC_KVP_SCHEMA_NAME:
            return observations
        for item in fields:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            value = item.get("value")
            if not name or should_drop_observation(name, value):
                continue
            observations.append(
                observation(
                    field_name=str(name),
                    value=value,
                    family=model_output_schema_name,
                    confidence=number_value(item.get("confidence")),
                    source_text=item.get("source_text"),
                    evidence_context=evidence_context,
                )
            )
        return observations
    if model_output_schema_name == GENERIC_KVP_SCHEMA_NAME:
        return observations
    allowed_keys = direct_observation_field_keys(model_output_schema_name)
    for key, value in payload.items():
        if allowed_keys is not None and key not in allowed_keys:
            continue
        if should_drop_observation(key, value):
            continue
        observations.append(
            observation(
                field_name=str(key),
                value=value,
                family=model_output_schema_name,
                confidence=None,
                source_text=value,
                evidence_context=evidence_context,
            )
        )
    return observations


def direct_observation_field_keys(
    model_output_schema_name: str | None,
) -> frozenset[str]:
    if model_output_schema_name is None or model_output_schema_name == GENERIC_KVP_SCHEMA_NAME:
        return frozenset()
    try:
        schema = load_model_output_schema(model_output_schema_name).schema
    except (OSError, ValueError, KeyError):
        return frozenset()
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return frozenset()
    return frozenset(str(key) for key in properties if key not in DIRECT_OBSERVATION_METADATA_KEYS)


def observation_dicts_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    observations = payload.get("observations")
    if not isinstance(observations, list):
        return []
    return [dict(item) for item in observations if isinstance(item, dict)]


def observation(
    *,
    field_name: str,
    value: Any,
    family: str | None,
    confidence: float | None,
    source_text: object,
    evidence_context: EvidenceContext | None,
) -> dict[str, Any]:
    bounded_source_text = bounded_text(source_text, max_length=500)
    return {
        "family": family,
        "field_name": field_name,
        "value": value,
        "value_type": value_type(value),
        "source_text": bounded_source_text,
        "confidence": confidence,
        "evidence": [
            _evidence(
                bounded_source_text if bounded_source_text else field_name,
                evidence_context,
            )
        ],
    }


def should_drop_observation(key: object, value: object) -> bool:
    normalized_key = str(key or "").strip().lower()
    if normalized_key in DROP_FLAT_OBSERVATION_KEYS:
        return True
    if value in (None, ""):
        return True
    if isinstance(value, (list, dict)) and not value:
        return True
    return contains_instruction_echo(key) or contains_instruction_echo(value)


def contains_instruction_echo(value: object) -> bool:
    if isinstance(value, str):
        text = value.lower()
        return any(phrase in text for phrase in ECHO_PHRASES)
    if isinstance(value, dict):
        return any(
            contains_instruction_echo(key) or contains_instruction_echo(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_instruction_echo(item) for item in value)
    return False


def _evidence(
    source_text: object,
    evidence_context: EvidenceContext | None,
) -> dict[str, Any]:
    text = str(source_text or "").strip()
    if evidence_context is not None:
        return evidence_ref_from_context(evidence_context=evidence_context, source_text=text)
    return {
        "source_engine": "granite_vision_3b",
        "source_text": text,
        "confidence": 0.72,
    }
