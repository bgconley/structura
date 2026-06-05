from __future__ import annotations

from copy import deepcopy
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
from lib.extraction.claim_aggregate_reconciliation import (
    resolve_claim_regions_for_family,
)
from lib.extraction.region_envelope import RegionExtractionEnvelope
from lib.extraction.region_reconciliation import RegionExtraction


def reconcile_invoice_region_extractions(
    *,
    document_id: UUID,
    seller: dict[str, Any],
    created_at: datetime,
    regions: list[RegionExtraction],
) -> dict[str, Any] | None:
    invoice: dict[str, Any] = {}
    totals: dict[str, Any] = {}
    claim_regions = resolve_claim_regions_for_family(
        family="invoice",
        missing_claims_reason="claims_required_for_invoice_aggregate",
        regions=regions,
    )
    if claim_regions is None:
        return None
    metadata = claim_regions.metadata
    claim_projection = claim_regions.claim_projection
    if claim_projection.family != "invoice":
        return None

    for region in regions:
        if region.region_envelope is not None:
            _merge_envelope_metadata(metadata, region.region_envelope)

    _merge_projection_fields(invoice, totals, claim_projection.fields)
    line_items = claim_projection.line_items
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


def _merge_projection_fields(
    invoice: dict[str, Any],
    totals: dict[str, Any],
    fields: dict[str, dict[str, Any]],
) -> None:
    for key, value in fields.get("invoice", {}).items():
        cleaned = _clean_canonical_scalar(value)
        if cleaned not in (None, ""):
            invoice[key] = deepcopy(cleaned)
    for key, value in fields.get("totals", {}).items():
        if isinstance(value, dict) and value.get("amount") is not None:
            totals[key] = deepcopy(value)


def _merge_envelope_metadata(
    metadata: dict[str, Any],
    envelope: RegionExtractionEnvelope,
) -> None:
    coverage_metadata = envelope.coverage.get("metadata")
    if not isinstance(coverage_metadata, dict):
        return
    payment_summary = coverage_metadata.get("payment_summary")
    if isinstance(payment_summary, dict):
        metadata["payment_summary"] = deepcopy(payment_summary)


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
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _renumber(line_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**item, "ordinal": index} for index, item in enumerate(line_items, start=1)]


def _clean_canonical_scalar(value: object) -> object | None:
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _party_has_non_placeholder_name(value: dict[str, Any]) -> bool:
    display_name = _clean_canonical_scalar(value.get("display_name"))
    return isinstance(display_name, str) and bool(display_name.strip())
