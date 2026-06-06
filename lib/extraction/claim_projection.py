from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any
from uuid import UUID

from lib.extraction.claim_registry import CLAIM_FAMILY_REGISTRIES, ClaimFamilyRegistry
from lib.extraction.claim_resolver import ClaimFamilyProjection


def project_claim_family_payload(
    *,
    document_id: UUID,
    created_at: datetime,
    projection: ClaimFamilyProjection,
    metadata: dict[str, Any],
    extra_containers: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    registry = CLAIM_FAMILY_REGISTRIES.get(projection.family)
    if registry is None or registry.aggregate_schema_name is None:
        return None

    containers = _projected_containers(projection, registry)
    line_items = _projected_line_items(projection, registry)
    if not _has_material_output(containers, line_items):
        return None

    payload: dict[str, Any] = {
        "schema_name": registry.aggregate_schema_name,
        "schema_version": registry.aggregate_schema_version,
        "document_id": str(document_id),
    }
    if extra_containers:
        payload.update({key: _clean_value(value) for key, value in extra_containers.items()})
    payload.update(containers)
    if registry.aggregate_line_items_key is not None:
        payload[registry.aggregate_line_items_key] = line_items
    payload.update(
        {
            "validation": {"needs_review": True, "checks": []},
            "created_at": created_at.isoformat(),
            "metadata": metadata,
        }
    )
    return payload


def project_document_observation_payload(
    *,
    document_id: UUID,
    created_at: datetime,
    projection: ClaimFamilyProjection,
    metadata: dict[str, Any],
) -> dict[str, Any] | None:
    if projection.family != "document_observation" or not projection.observations:
        return None

    return {
        "schema_name": "document_observation",
        "schema_version": "v1",
        "document_id": str(document_id),
        "observations": _clean_value(projection.observations),
        "confidence": {},
        "validation": {"needs_review": True, "checks": []},
        "created_at": created_at.isoformat(),
        "metadata": _clean_value(metadata),
    }


def _projected_containers(
    projection: ClaimFamilyProjection,
    registry: ClaimFamilyRegistry,
) -> dict[str, Any]:
    containers: dict[str, Any] = {}
    for name in registry.aggregate_required_containers:
        containers[name] = _clean_container(projection.fields.get(name))
    for name in registry.aggregate_optional_containers:
        container = _clean_container(projection.fields.get(name))
        if container:
            containers[name] = container
    return containers


def _projected_line_items(
    projection: ClaimFamilyProjection,
    registry: ClaimFamilyRegistry,
) -> list[dict[str, Any]]:
    if registry.aggregate_line_items_key is None:
        return []
    items: list[dict[str, Any]] = []
    required_field = registry.aggregate_line_item_required_field
    for item in projection.line_items:
        cleaned = _clean_container(item)
        if required_field is not None and cleaned.get(required_field) in (None, ""):
            continue
        if cleaned:
            items.append(cleaned)
    return [{**item, "ordinal": index} for index, item in enumerate(items, start=1)]


def _has_material_output(
    containers: dict[str, Any],
    line_items: list[dict[str, Any]],
) -> bool:
    return any(value not in (None, "", [], {}) for value in containers.values()) or bool(line_items)


def _clean_container(fields: dict[str, Any] | None) -> dict[str, Any]:
    if not fields:
        return {}
    return {
        key: _clean_value(value) for key, value in fields.items() if value not in (None, "", [], {})
    }


def _clean_value(value: Any) -> Any:
    return deepcopy(value)
