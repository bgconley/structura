from __future__ import annotations

import json
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
from lib.extraction.claim_resolver import resolve_claims_for_family
from lib.extraction.invoice_legacy_reconciliation import (
    legacy_invoice_line_item_dicts_from_region,
    legacy_invoice_payment_summary_from_region,
    merge_legacy_money_fields,
)
from lib.extraction.region_envelope import (
    EvidenceRef,
    RegionExtractionEnvelope,
    RegionFact,
    RegionLineItem,
)
from lib.extraction.region_reconciliation import RegionExtraction

FORBIDDEN_CANONICAL_PLACEHOLDERS = {
    "unknown",
    "n/a",
    "none",
    "null",
    "missing",
    "not found",
}


def reconcile_invoice_region_extractions(
    *,
    document_id: UUID,
    seller: dict[str, Any],
    created_at: datetime,
    regions: list[RegionExtraction],
    document_fallback: dict[str, Any] | None = None,
    allow_legacy_region_envelopes: bool = False,
    allow_legacy_raw_payloads: bool = False,
) -> dict[str, Any] | None:
    line_items: list[dict[str, Any]] = []
    invoice: dict[str, Any] = {}
    totals: dict[str, Any] = {}
    source_families: set[str] = set()
    metadata: dict[str, Any] = {"region_extractions": []}
    reconciled_region_count = 0

    for region in regions:
        if region.claims:
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
            reconciled_region_count += 1
            claim_projection = resolve_claims_for_family(
                family="invoice",
                claims=list(region.claims),
            )
            line_items.extend(claim_projection.line_items)
            _merge_projection_fields(invoice, totals, claim_projection.fields)
            if claim_projection.decisions:
                metadata.setdefault("claim_resolution_decisions", []).extend(
                    decision.__dict__ for decision in claim_projection.decisions
                )
            if region.region_envelope is not None:
                _merge_envelope_metadata(metadata, region.region_envelope)
            continue

        if region.region_envelope is not None:
            if not allow_legacy_region_envelopes:
                metadata.setdefault("skipped_region_extractions", []).append(
                    {
                        **_region_reference(region),
                        "reason": "legacy_region_envelope_reconciliation_disabled",
                    }
                )
                continue
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
            reconciled_region_count += 1
            line_items.extend(_line_item_dicts_from_envelope(region))
            _merge_invoice_facts_from_envelope(
                invoice,
                totals,
                region.region_envelope,
            )
            _merge_envelope_metadata(metadata, region.region_envelope)
            continue

        if not allow_legacy_raw_payloads:
            metadata.setdefault("skipped_region_extractions", []).append(
                {
                    **_region_reference(region),
                    "reason": "legacy_raw_payload_reconciliation_disabled",
                }
            )
            continue

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
        reconciled_region_count += 1
        if region.semantic_type.endswith("line_item_table"):
            line_items.extend(legacy_invoice_line_item_dicts_from_region(region))
            merge_legacy_money_fields(totals, payload.get("totals"))
            continue
        if region.semantic_type == "payment_summary":
            summary = legacy_invoice_payment_summary_from_region(region)
            if summary.get("invoice_number"):
                invoice["invoice_number"] = summary["invoice_number"]
            if summary.get("amount_paid"):
                totals["amount_paid"] = summary["amount_paid"]
            if summary.get("payment_summary"):
                metadata["payment_summary"] = summary["payment_summary"]
            continue
        merge_legacy_money_fields(totals, payload.get("totals"))

    if source_families:
        metadata["source_families"] = sorted(source_families)
    if reconciled_region_count == 0:
        return None
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


def _line_item_dicts_from_envelope(region: RegionExtraction) -> list[dict[str, Any]]:
    envelope = region.region_envelope
    if envelope is None:
        return []
    line_items: list[dict[str, Any]] = []
    for item in envelope.line_items:
        payload = _line_item_dict_from_envelope_item(item, region)
        if payload:
            line_items.append(payload)
    return line_items


def _line_item_dict_from_envelope_item(
    item: RegionLineItem,
    region: RegionExtraction,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for target_key, value in (
        ("description", item.description),
        ("code", item.code),
        ("quantity", item.quantity),
        ("unit", item.unit),
        ("service_date", item.service_date),
        ("category_hint", item.category_hint),
        ("table_id", item.table_id),
        ("row_index", item.row_index),
        ("page_number", item.page_number),
    ):
        if value not in (None, ""):
            payload[target_key] = value
    if item.unit_price is not None:
        payload["unit_price"] = _money_payload(item.unit_price, item.currency_code)
    if item.gross_amount is not None:
        payload["gross_amount"] = _money_payload(item.gross_amount, item.currency_code)
    if item.tax_amount is not None:
        payload["tax_amount"] = _money_payload(item.tax_amount, item.currency_code)
    if item.net_amount is not None:
        payload["amount"] = _money_payload(item.net_amount, item.currency_code)
    evidence = _envelope_evidence(item.evidence, region)
    if evidence:
        payload["evidence"] = evidence
    has_value = any(
        payload.get(key) not in (None, "")
        for key in (
            "description",
            "code",
            "quantity",
            "unit_price",
            "gross_amount",
            "tax_amount",
            "amount",
        )
    )
    return payload if has_value else {}


def _merge_invoice_facts_from_envelope(
    invoice: dict[str, Any],
    totals: dict[str, Any],
    envelope: RegionExtractionEnvelope,
) -> None:
    for fact in envelope.facts:
        invoice_key = _invoice_key_for_fact(fact)
        if invoice_key:
            value = _clean_canonical_scalar(fact.value)
            if value not in (None, ""):
                invoice[invoice_key] = deepcopy(value)
            continue
        totals_key = _totals_key_for_fact(fact)
        if totals_key:
            money_value = _money_value_from_fact(fact)
            if money_value is not None:
                totals[totals_key] = money_value


def _invoice_key_for_fact(fact: RegionFact) -> str | None:
    return {
        "invoice.invoice_number": "invoice_number",
        "invoice.issue_date": "issued_on",
        "invoice.due_date": "due_on",
    }.get(fact.name)


def _totals_key_for_fact(fact: RegionFact) -> str | None:
    return {
        "invoice.subtotal": "subtotal",
        "invoice.tax_total": "tax_total",
        "invoice.total_amount": "total",
        "invoice.balance_due": "balance_due",
        "invoice.amount_paid": "amount_paid",
    }.get(fact.name)


def _money_value_from_fact(fact: RegionFact) -> dict[str, Any] | None:
    if fact.value_type != "money" or not isinstance(fact.value, dict):
        return None
    amount = fact.value.get("amount")
    if amount is None:
        return None
    payload = {"amount": amount}
    currency = fact.value.get("currency") or fact.value.get("currency_code")
    if currency not in (None, ""):
        payload["currency"] = currency
    return payload


def _money_payload(amount: float, currency_code: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"amount": amount}
    if currency_code not in (None, ""):
        payload["currency"] = currency_code
    return payload


def _envelope_evidence(
    refs: list[EvidenceRef],
    region: RegionExtraction,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for ref in refs:
        payload = ref.model_dump(mode="json", exclude_none=True)
        payload.setdefault("semantic_region_id", str(region.semantic_region_id))
        evidence.append(payload)
    return evidence


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
