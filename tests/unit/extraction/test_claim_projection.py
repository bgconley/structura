from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from lib.extraction.claim_projection import (
    project_claim_family_payload,
    project_document_observation_payload,
)
from lib.extraction.claim_resolver import ClaimFamilyProjection, resolve_claims_for_family
from lib.extraction.claims import Claim, ClaimAnchor, ClaimSourceEngine


def test_registry_projection_builds_invoice_payload_shape() -> None:
    document_id = uuid4()
    created_at = datetime.now(UTC)
    projection = ClaimFamilyProjection(
        family="invoice",
        fields={
            "invoice": {"invoice_number": "INV-42"},
            "totals": {
                "subtotal": {"amount": 100.0, "currency": "USD"},
                "total": {"amount": 108.0, "currency": "USD"},
            },
        },
        line_items=[
            {
                "description": "Labor",
                "amount": {"amount": 100.0, "currency": "USD"},
                "evidence": [{"page_number": 1, "table_id": "invoice-table", "row_index": 2}],
            }
        ],
    )

    payload = project_claim_family_payload(
        document_id=document_id,
        created_at=created_at,
        projection=projection,
        metadata={"quality_outcome": "extracted_cleanly"},
        extra_containers={"seller": {"display_name": "MAX BMW", "party_type": "company"}},
    )

    assert payload == {
        "schema_name": "invoice",
        "schema_version": "v1",
        "document_id": str(document_id),
        "seller": {"display_name": "MAX BMW", "party_type": "company"},
        "invoice": {"invoice_number": "INV-42"},
        "line_items": [
            {
                "description": "Labor",
                "amount": {"amount": 100.0, "currency": "USD"},
                "evidence": [{"page_number": 1, "table_id": "invoice-table", "row_index": 2}],
                "ordinal": 1,
            }
        ],
        "totals": {
            "subtotal": {"amount": 100.0, "currency": "USD"},
            "total": {"amount": 108.0, "currency": "USD"},
        },
        "validation": {"needs_review": True, "checks": []},
        "created_at": created_at.isoformat(),
        "metadata": {"quality_outcome": "extracted_cleanly"},
    }


def test_registry_projection_builds_medical_eob_payload_shape() -> None:
    document_id = uuid4()
    created_at = datetime.now(UTC)
    projection = ClaimFamilyProjection(
        family="medical_eob",
        fields={
            "payer": {"display_name": "Anthem Blue Cross"},
            "patient": {"display_name": "Jane Patient"},
            "provider": {},
            "claim": {"claim_number": "CLM-123"},
            "financial_summary": {
                "total_patient_responsibility": {"amount": 62.0, "currency": "USD"}
            },
        },
        line_items=[
            {
                "service_description": "Office visit",
                "patient_responsibility": {"amount": 62.0, "currency": "USD"},
                "evidence": [{"page_number": 2, "table_id": "eob-table", "row_index": 4}],
            }
        ],
    )

    payload = project_claim_family_payload(
        document_id=document_id,
        created_at=created_at,
        projection=projection,
        metadata={"quality_outcome": "extracted_cleanly"},
    )

    assert payload == {
        "schema_name": "medical_eob",
        "schema_version": "v1",
        "document_id": str(document_id),
        "payer": {"display_name": "Anthem Blue Cross"},
        "patient": {"display_name": "Jane Patient"},
        "claim": {"claim_number": "CLM-123"},
        "service_lines": [
            {
                "service_description": "Office visit",
                "patient_responsibility": {"amount": 62.0, "currency": "USD"},
                "evidence": [{"page_number": 2, "table_id": "eob-table", "row_index": 4}],
                "ordinal": 1,
            }
        ],
        "financial_summary": {"total_patient_responsibility": {"amount": 62.0, "currency": "USD"}},
        "validation": {"needs_review": True, "checks": []},
        "created_at": created_at.isoformat(),
        "metadata": {"quality_outcome": "extracted_cleanly"},
    }


def test_registry_projection_builds_receipt_payload_shape() -> None:
    document_id = uuid4()
    created_at = datetime.now(UTC)
    projection = ClaimFamilyProjection(
        family="receipt",
        fields={
            "merchant": {"display_name": "Corner Cafe"},
            "transaction": {
                "date_local": "2026-06-12",
                "subtotal": {"amount": 12.0, "currency": "USD"},
                "tax": {"amount": 1.02, "currency": "USD"},
                "tip": {"amount": 2.0, "currency": "USD"},
                "discount_total": {"amount": 1.0, "currency": "USD"},
                "total": {"amount": 14.02, "currency": "USD"},
            },
        },
        line_items=[
            {
                "description": "Coffee beans",
                "sku": "BEANS-12",
                "quantity": 2.0,
                "unit_price": {"amount": 6.0, "currency": "USD"},
                "discount": {"amount": 1.0, "currency": "USD"},
                "amount": {"amount": 11.0, "currency": "USD"},
                "tax_category_hint": "grocery",
                "category_hint": "food",
                "evidence": [{"page_number": 1, "table_id": "receipt-table", "row_index": 1}],
            }
        ],
    )

    payload = project_claim_family_payload(
        document_id=document_id,
        created_at=created_at,
        projection=projection,
        metadata={"quality_outcome": "extracted_cleanly"},
    )

    assert payload == {
        "schema_name": "receipt",
        "schema_version": "v1",
        "document_id": str(document_id),
        "merchant": {"display_name": "Corner Cafe"},
        "transaction": {
            "date_local": "2026-06-12",
            "subtotal": {"amount": 12.0, "currency": "USD"},
            "tax": {"amount": 1.02, "currency": "USD"},
            "tip": {"amount": 2.0, "currency": "USD"},
            "discount_total": {"amount": 1.0, "currency": "USD"},
            "total": {"amount": 14.02, "currency": "USD"},
        },
        "line_items": [
            {
                "description": "Coffee beans",
                "sku": "BEANS-12",
                "quantity": 2.0,
                "unit_price": {"amount": 6.0, "currency": "USD"},
                "discount": {"amount": 1.0, "currency": "USD"},
                "amount": {"amount": 11.0, "currency": "USD"},
                "tax_category_hint": "grocery",
                "category_hint": "food",
                "evidence": [{"page_number": 1, "table_id": "receipt-table", "row_index": 1}],
                "ordinal": 1,
            }
        ],
        "validation": {"needs_review": True, "checks": []},
        "created_at": created_at.isoformat(),
        "metadata": {"quality_outcome": "extracted_cleanly"},
    }


def test_service_record_claims_project_as_review_only_observations() -> None:
    anchor = ClaimAnchor(page_number=1, table_id="service-table", row_index=2)
    projection = resolve_claims_for_family(
        family="document_observation",
        claims=[
            _claim(
                canonical_key="service_record.line_item.description",
                typed_value="600 mile running-in check",
                source_engine="docling",
                anchor=anchor,
            ),
            _claim(
                canonical_key="service_record.line_item.amount",
                typed_value={"amount": 185.0, "currency": "USD"},
                source_engine="docling",
                anchor=anchor,
            ),
            _claim(
                canonical_key="service_record.total",
                typed_value={"amount": 209.81, "currency": "USD"},
                source_engine="docling",
                anchor=anchor,
            ),
        ],
    )

    payload = project_document_observation_payload(
        document_id=uuid4(),
        created_at=datetime.now(UTC),
        projection=projection,
        metadata={"source_families": ["service_record"]},
    )

    assert payload is not None
    observations = {(item["family"], item["field_name"]): item for item in payload["observations"]}
    assert set(observations) == {
        ("service_record", "line_item.amount"),
        ("service_record", "line_item.description"),
        ("service_record", "total"),
    }
    assert observations[("service_record", "line_item.description")]["value"] == (
        "600 mile running-in check"
    )
    assert observations[("service_record", "line_item.amount")]["value"] == {
        "amount": 185.0,
        "currency": "USD",
    }


def test_retail_order_claims_project_as_review_only_observations() -> None:
    anchor = ClaimAnchor(page_number=2, table_id="order-table", row_index=1)
    projection = resolve_claims_for_family(
        family="document_observation",
        claims=[
            _claim(
                canonical_key="retail_order.merchant_name",
                typed_value="Apple Store",
                source_engine="docling",
                anchor=anchor,
            ),
            _claim(
                canonical_key="retail_order.order_number",
                typed_value="W123456789",
                source_engine="docling",
                anchor=anchor,
            ),
            _claim(
                canonical_key="retail_order.line_item.description",
                typed_value="Replacement charging cable",
                source_engine="docling",
                anchor=anchor,
            ),
            _claim(
                canonical_key="retail_order.line_item.amount",
                typed_value={"amount": 25.0, "currency": "USD"},
                source_engine="docling",
                anchor=anchor,
            ),
        ],
    )

    payload = project_document_observation_payload(
        document_id=uuid4(),
        created_at=datetime.now(UTC),
        projection=projection,
        metadata={"source_families": ["retail_order"]},
    )

    assert payload is not None
    observations = {(item["family"], item["field_name"]): item for item in payload["observations"]}
    assert set(observations) == {
        ("retail_order", "line_item.amount"),
        ("retail_order", "line_item.description"),
        ("retail_order", "merchant_name"),
        ("retail_order", "order_number"),
    }
    assert observations[("retail_order", "merchant_name")]["value"] == "Apple Store"
    assert observations[("retail_order", "line_item.amount")]["value_type"] == "json"


def test_observation_projection_covers_mortgage_title_and_generic_families() -> None:
    anchor = ClaimAnchor(page_number=3, table_id="kvp-table", row_index=1)
    projection = resolve_claims_for_family(
        family="document_observation",
        claims=[
            _claim(
                canonical_key="mortgage_escrow_statement.loan_number",
                typed_value="0176595130",
                source_engine="docling",
                anchor=anchor,
            ),
            _claim(
                canonical_key="real_estate_title.seller_name",
                typed_value="Jane Seller",
                source_engine="docling",
                anchor=anchor,
            ),
            _claim(
                canonical_key="generic_document.notice_date",
                typed_value="2026-06-12",
                source_engine="docling",
                anchor=anchor,
            ),
        ],
    )

    payload = project_document_observation_payload(
        document_id=uuid4(),
        created_at=datetime.now(UTC),
        projection=projection,
        metadata={
            "source_families": [
                "generic_document",
                "mortgage_escrow_statement",
                "real_estate_title",
            ]
        },
    )

    assert payload is not None
    observations = {(item["family"], item["field_name"]): item for item in payload["observations"]}
    assert set(observations) == {
        ("generic_document", "notice_date"),
        ("mortgage_escrow_statement", "loan_number"),
        ("real_estate_title", "seller_name"),
    }
    assert observations[("mortgage_escrow_statement", "loan_number")]["source_text"] == "0176595130"


def test_projection_builds_document_observation_payload_shape() -> None:
    document_id = uuid4()
    created_at = datetime.now(UTC)
    projection = ClaimFamilyProjection(
        family="document_observation",
        observations=[
            {
                "family": "real_estate_title",
                "field_name": "property.address",
                "value": "123 Main St",
                "value_type": "string",
                "source_text": "123 Main St",
                "confidence": 0.82,
                "evidence": [{"page_number": 2, "element_id": "el-2"}],
            }
        ],
    )

    payload = project_document_observation_payload(
        document_id=document_id,
        created_at=created_at,
        projection=projection,
        metadata={"quality_outcome": "needs_human_review"},
    )

    assert payload == {
        "schema_name": "document_observation",
        "schema_version": "v1",
        "document_id": str(document_id),
        "observations": [
            {
                "family": "real_estate_title",
                "field_name": "property.address",
                "value": "123 Main St",
                "value_type": "string",
                "source_text": "123 Main St",
                "confidence": 0.82,
                "evidence": [{"page_number": 2, "element_id": "el-2"}],
            }
        ],
        "confidence": {},
        "validation": {"needs_review": True, "checks": []},
        "created_at": created_at.isoformat(),
        "metadata": {"quality_outcome": "needs_human_review"},
    }


def test_registry_projection_returns_none_for_empty_family_projection() -> None:
    payload = project_claim_family_payload(
        document_id=uuid4(),
        created_at=datetime.now(UTC),
        projection=ClaimFamilyProjection(family="medical_eob"),
        metadata={},
    )

    assert payload is None


def _claim(
    *,
    canonical_key: str,
    typed_value: object,
    source_engine: ClaimSourceEngine,
    anchor: ClaimAnchor,
) -> Claim:
    return Claim(
        claim_id=f"{source_engine}:{canonical_key}:{typed_value}",
        document_id="doc-1",
        source_engine=source_engine,
        anchor=anchor,
        canonical_key=canonical_key,
        raw_value=str(typed_value),
        typed_value=typed_value,
        value_type="money" if isinstance(typed_value, dict) else "text",
        confidence=None,
        method="test",
        evidence=(anchor.as_json(),),
    )
