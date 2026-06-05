from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any
from uuid import UUID

from lib.extraction.claim_aggregate_reconciliation import (
    resolve_claim_regions_for_family,
)
from lib.extraction.region_reconciliation import RegionExtraction


def reconcile_medical_eob_region_extractions(
    *,
    document_id: UUID,
    created_at: datetime,
    regions: list[RegionExtraction],
) -> dict[str, Any] | None:
    claim_regions = resolve_claim_regions_for_family(
        family="medical_eob",
        missing_claims_reason="claims_required_for_medical_eob_aggregate",
        regions=regions,
    )
    if claim_regions is None:
        return None
    projection = claim_regions.claim_projection
    if projection.family != "medical_eob":
        return None
    metadata = claim_regions.metadata

    payer = _party_fields(projection.fields.get("payer"))
    patient = _party_fields(projection.fields.get("patient"))
    provider = _party_fields(projection.fields.get("provider"))
    claim = _clean_container(projection.fields.get("claim"))
    financial_summary = _clean_container(projection.fields.get("financial_summary"))
    service_lines = _renumber_service_lines(projection.line_items)

    if not payer and not patient and not claim and not financial_summary and not service_lines:
        return None

    payload: dict[str, Any] = {
        "schema_name": "medical_eob",
        "schema_version": "v1",
        "document_id": str(document_id),
        "payer": payer,
        "patient": patient,
        "claim": claim,
        "service_lines": service_lines,
        "financial_summary": financial_summary,
        "validation": {"needs_review": True, "checks": []},
        "created_at": created_at.isoformat(),
        "metadata": metadata,
    }
    if provider:
        payload["provider"] = provider
    return payload


def _party_fields(fields: dict[str, Any] | None) -> dict[str, Any]:
    return _clean_container(fields)


def _clean_container(fields: dict[str, Any] | None) -> dict[str, Any]:
    if not fields:
        return {}
    return {
        key: deepcopy(value) for key, value in fields.items() if value not in (None, "", [], {})
    }


def _renumber_service_lines(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    service_lines: list[dict[str, Any]] = []
    for ordinal, item in enumerate(items, start=1):
        service_line = {
            key: deepcopy(value) for key, value in item.items() if value not in (None, "", [], {})
        }
        if service_line.get("service_description") in (None, ""):
            continue
        service_line["ordinal"] = ordinal
        service_lines.append(service_line)
    return service_lines
