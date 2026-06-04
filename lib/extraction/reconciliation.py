from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from lib.extraction.candidate_value_parsing import (
    float_key,
    money_amount,
    money_currency,
    normalized_text_key,
    number_value,
)
from lib.extraction.model_output_normalization import (
    invoice_line_item_dicts_from_payload,
    invoice_payment_summary_from_payload,
)

FORBIDDEN_CANONICAL_PLACEHOLDERS = {
    "unknown",
    "n/a",
    "none",
    "null",
    "missing",
    "not found",
}


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
    document_fallback: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    line_items: list[dict[str, Any]] = []
    invoice: dict[str, Any] = {}
    totals: dict[str, Any] = {}
    source_families: set[str] = set()
    metadata: dict[str, Any] = {"region_extractions": []}

    for region in regions:
        payload = region.normalized_json
        if not _region_source_family_is_invoice_compatible(region):
            metadata.setdefault("skipped_region_extractions", []).append(
                {
                    **_region_reference(region),
                    "reason": "aggregate_incompatible_source_family",
                    "source_family": _region_source_family(region),
                }
            )
            continue
        source_family = _region_source_family(region)
        if source_family:
            source_families.add(source_family)
        metadata["region_extractions"].append(_region_reference(region))
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

    if source_families:
        metadata["source_families"] = sorted(source_families)
    _merge_document_fallback(invoice, totals, document_fallback or {})
    if not line_items and not invoice and not totals:
        return None
    if not invoice.get("invoice_number"):
        metadata.setdefault("missing_fields", []).append("invoice.invoice_number")
        invoice.pop("invoice_number", None)
    if not _party_has_non_placeholder_name(seller):
        metadata.setdefault("missing_fields", []).append("seller.display_name")
        seller = {}
    if "total" not in totals and "amount_paid" in totals:
        totals["total"] = totals["amount_paid"]
    if "total" not in totals:
        metadata.setdefault("missing_fields", []).append("totals.total")

    return {
        "schema_name": "invoice",
        "schema_version": "v1",
        "document_id": str(document_id),
        "seller": seller,
        "invoice": invoice,
        "line_items": _renumber(_dedupe_line_item_dicts(line_items)),
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
                evidence.append(
                    {
                        "semantic_region_id": str(region.semantic_region_id),
                        **dict(evidence_item),
                    }
                )
        copied["evidence"] = evidence
        enriched.append(copied)
    return enriched


def _dedupe_line_item_dicts(line_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in line_items:
        key = _line_item_key(item)
        current = deduped.get(key)
        if current is None or _line_item_richness(item) > _line_item_richness(current):
            deduped[key] = item
    return list(deduped.values())


def _line_item_key(item: dict[str, Any]) -> tuple[Any, ...]:
    amount = item.get("amount")
    return (
        normalized_text_key(item.get("description")),
        normalized_text_key(item.get("code") or item.get("sku")),
        float_key(number_value(item.get("quantity"))),
        float_key(money_amount(item.get("unit_price"))),
        float_key(money_amount(item.get("gross_amount"))),
        float_key(money_amount(item.get("net_amount") or amount)),
        normalized_text_key(
            item.get("currency")
            or money_currency(item.get("net_amount"))
            or money_currency(amount)
            or money_currency(item.get("gross_amount"))
        ),
        _line_item_locator_key(item),
    )


def _line_item_locator_key(item: dict[str, Any]) -> tuple[Any, ...]:
    evidence = item.get("evidence")
    first = evidence[0] if isinstance(evidence, list) and evidence else {}
    if not isinstance(first, dict):
        first = {}
    return (
        normalized_text_key(first.get("semantic_region_id")),
        first.get("page_number") or item.get("page_number"),
        normalized_text_key(first.get("page_id") or item.get("page_id")),
        normalized_text_key(first.get("element_id") or item.get("element_id")),
        normalized_text_key(first.get("table_id") or item.get("table_id")),
        first.get("row_index") if first.get("row_index") is not None else item.get("row_index"),
        _json_key(first.get("bbox") or item.get("bbox")),
    )


def _line_item_richness(item: dict[str, Any]) -> int:
    values = (
        item.get("code") or item.get("sku"),
        item.get("service_date"),
        item.get("quantity"),
        item.get("unit"),
        item.get("unit_price"),
        item.get("gross_amount"),
        item.get("discount_amount"),
        item.get("tax_amount"),
        item.get("net_amount"),
        item.get("amount"),
        item.get("currency"),
        item.get("category_hint") or item.get("gl_hint"),
    )
    evidence = item.get("evidence")
    return sum(value not in (None, "") for value in values) + (
        len(evidence) if isinstance(evidence, list) else 0
    )


def _json_key(value: Any) -> str:
    if value is None:
        return ""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _region_reference(region: RegionExtraction) -> dict[str, str]:
    return {
        "extraction_id": str(region.extraction_id),
        "semantic_region_id": str(region.semantic_region_id),
        "semantic_type": region.semantic_type,
    }


def _region_source_family_is_invoice_compatible(region: RegionExtraction) -> bool:
    source_family = _region_source_family(region)
    return source_family in {"", "invoice"}


def _region_source_family(region: RegionExtraction) -> str:
    value = region.normalized_json.get("schema_name")
    if value in (None, ""):
        metadata = region.normalized_json.get("metadata")
        if isinstance(metadata, dict):
            value = metadata.get("source_family") or metadata.get("document_family")
    return normalized_text_key(value)


def _merge_money_fields(target: dict[str, Any], source: object) -> None:
    if not isinstance(source, dict):
        return
    for key in ("subtotal", "tax_total", "total", "amount_paid", "balance_due"):
        value = source.get(key)
        if isinstance(value, dict) and value.get("amount") is not None:
            target[key] = value


def _merge_document_fallback(
    invoice: dict[str, Any],
    totals: dict[str, Any],
    fallback: dict[str, Any],
) -> None:
    if not invoice.get("invoice_number"):
        invoice_number = fallback.get("invoice_number") or fallback.get("invoice_no")
        invoice_number = _clean_canonical_scalar(invoice_number)
        if invoice_number:
            invoice["invoice_number"] = str(invoice_number)
    if not invoice.get("issued_on"):
        issued_on = _local_date(fallback.get("date") or fallback.get("issued_on"))
        if issued_on:
            invoice["issued_on"] = issued_on
    if "total" not in totals:
        total = fallback.get("total_amount") or fallback.get("amount_due")
        if isinstance(total, dict) and total.get("amount") is not None:
            totals["total"] = total


def _local_date(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _renumber(line_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**item, "ordinal": index} for index, item in enumerate(line_items, start=1)]


def _clean_canonical_scalar(value: object) -> object | None:
    if isinstance(value, str) and value.strip().lower() in FORBIDDEN_CANONICAL_PLACEHOLDERS:
        return None
    return value


def _party_has_non_placeholder_name(value: dict[str, Any]) -> bool:
    display_name = _clean_canonical_scalar(value.get("display_name"))
    return isinstance(display_name, str) and bool(display_name.strip())
