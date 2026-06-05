from __future__ import annotations

from typing import Any, Protocol

from lib.extraction.model_output_normalization import (
    invoice_line_item_dicts_from_payload,
    invoice_payment_summary_from_payload,
)


class _LegacyInvoiceRegion(Protocol):
    @property
    def semantic_region_id(self) -> object: ...

    @property
    def normalized_json(self) -> dict[str, Any]: ...


def legacy_invoice_line_item_dicts_from_region(
    region: _LegacyInvoiceRegion,
) -> list[dict[str, Any]]:
    return _with_region_evidence(
        invoice_line_item_dicts_from_payload(region.normalized_json),
        region,
    )


def legacy_invoice_payment_summary_from_region(region: _LegacyInvoiceRegion) -> dict[str, Any]:
    return invoice_payment_summary_from_payload(region.normalized_json)


def merge_legacy_money_fields(target: dict[str, Any], source: object) -> None:
    if not isinstance(source, dict):
        return
    for key in ("subtotal", "tax_total", "total", "amount_paid", "balance_due"):
        value = source.get(key)
        if isinstance(value, dict) and value.get("amount") is not None:
            target[key] = value


def _with_region_evidence(
    line_items: list[dict[str, Any]],
    region: _LegacyInvoiceRegion,
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
