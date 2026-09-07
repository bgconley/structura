"""Map only persisted canonical line-item columns into the public read contract."""

from typing import Any

from lib.contracts.document_line_items import CanonicalLineItemRead


def canonical_line_item_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = {
        name: row.get(name)
        for name in (
            "id",
            "document_id",
            "line_item_type",
            "ordinal",
            "selected_candidate_id",
            "code",
            "code_system",
            "service_date",
            "description",
            "quantity",
            "unit",
            "unit_price",
            "gross_amount",
            "discount_amount",
            "tax_amount",
            "net_amount",
            "allowed_amount",
            "plan_paid_amount",
            "category_hint",
            "source_kind",
            "review_status",
            "accepted_at",
            "updated_at",
        )
    }
    payload.update(
        currency=row.get("currency_code"),
        evidence=row.get("evidence_json") or [],
        validation=row.get("validation_json") or {},
    )
    return CanonicalLineItemRead.model_validate(payload).model_dump(mode="json", by_alias=True)
