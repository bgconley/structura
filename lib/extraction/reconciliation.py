from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from lib.extraction.model_output_normalization import (
    invoice_line_item_dicts_from_payload,
    invoice_payment_summary_from_payload,
)


@dataclass(frozen=True)
class RegionExtraction:
    extraction_id: UUID
    semantic_region_id: UUID
    semantic_type: str
    normalized_json: dict[str, Any]


def reconcile_invoice_region_extractions(
    *,
    document_id: UUID,
    seller: dict[str, Any],
    created_at: datetime,
    regions: list[RegionExtraction],
) -> dict[str, Any]:
    line_items: list[dict[str, Any]] = []
    invoice: dict[str, Any] = {}
    totals: dict[str, Any] = {}
    metadata: dict[str, Any] = {
        "region_extractions": [
            {
                "extraction_id": str(region.extraction_id),
                "semantic_region_id": str(region.semantic_region_id),
                "semantic_type": region.semantic_type,
            }
            for region in regions
        ]
    }

    for region in regions:
        payload = region.normalized_json
        if region.semantic_type.endswith("line_item_table"):
            line_items.extend(
                _with_region_evidence(
                    invoice_line_item_dicts_from_payload(payload),
                    region,
                )
            )
            _merge_money_fields(totals, payload.get("totals"))
            continue
        if region.semantic_type == "payment_summary":
            summary = invoice_payment_summary_from_payload(payload)
            if summary.get("invoice_number"):
                invoice["invoice_number"] = summary["invoice_number"]
            if summary.get("amount_paid"):
                totals["amount_paid"] = summary["amount_paid"]
            if summary.get("payment_summary"):
                metadata["payment_summary"] = summary["payment_summary"]
            continue
        _merge_money_fields(totals, payload.get("totals"))

    if not invoice.get("invoice_number"):
        invoice["invoice_number"] = "unknown"
    if "total" not in totals and "amount_paid" in totals:
        totals["total"] = totals["amount_paid"]

    return {
        "schema_name": "invoice",
        "schema_version": "v1",
        "document_id": str(document_id),
        "seller": seller,
        "invoice": invoice,
        "line_items": _renumber(line_items),
        "totals": totals,
        "validation": {"needs_review": True, "checks": []},
        "created_at": created_at.isoformat(),
        "metadata": metadata,
    }


def _with_region_evidence(
    line_items: list[dict[str, Any]],
    region: RegionExtraction,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in line_items:
        copied = dict(item)
        evidence = []
        for evidence_item in item.get("evidence") or []:
            if isinstance(evidence_item, dict):
                evidence.append(dict(evidence_item))
        copied["evidence"] = evidence
        enriched.append(copied)
    return enriched


def _merge_money_fields(target: dict[str, Any], source: object) -> None:
    if not isinstance(source, dict):
        return
    for key in ("subtotal", "tax_total", "total", "amount_paid", "balance_due"):
        value = source.get(key)
        if isinstance(value, dict) and value.get("amount") is not None:
            target[key] = value


def _renumber(line_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**item, "ordinal": index} for index, item in enumerate(line_items, start=1)]
