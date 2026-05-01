from __future__ import annotations

from uuid import uuid4

from lib.extraction.classification import classify_document
from lib.extraction.evidence import EvidenceResolver, has_concrete_evidence
from lib.extraction.heuristics import invoice_payload
from lib.extraction.models import ExtractionSourceDocument, ParsedElementText, ParsedPageText
from lib.extraction.validators import validate_extraction_payload, validate_semantic_region_payload


def test_phase4_classifier_identifies_invoice_from_canonical_text() -> None:
    source = _source(
        """
        Seller: Acme Repairs
        Invoice Number: INV-100
        Issue Date: 2026-04-01
        Due Date: 2026-04-30
        Total: 1042.15
        """
    )

    decision = classify_document(source)

    assert decision.family == "invoice"
    assert decision.route_profile == "docling_plus_structured_extraction"
    assert decision.confidence >= 0.8


def test_phase8_qwen_route_eligible_marks_review_without_auto_model_escalation() -> None:
    source = _source(
        """
        Seller: Acme Repairs
        Invoice Number: INV-200
        Total: 88.00
        """,
        metadata={"phase8": {"quality": {"qwenRouteEligible": True}}},
    )

    decision = classify_document(source)

    assert decision.family == "invoice"
    assert decision.route_profile == "docling_plus_structured_extraction"
    assert decision.needs_review is True
    assert "phase8_qwen_route" in decision.payload["reasons"]


def test_phase4_receipt_validation_flags_arithmetic_mismatch() -> None:
    source = _source(
        "Merchant: Whole Foods\nDate: 2026-04-03\nSubtotal: 10.00\nTax: 1.00\nTotal: 20.00"
    )
    evidence = EvidenceResolver(source).for_value("Total: 20.00")
    payload = {
        "schema_name": "receipt",
        "schema_version": "v1",
        "document_id": str(source.document_id),
        "merchant": {"display_name": "Whole Foods", "evidence": evidence},
        "transaction": {
            "date_local": "2026-04-03",
            "subtotal": {"amount": 10.0, "currency": "USD"},
            "tax": {"amount": 1.0, "currency": "USD"},
            "total": {"amount": 20.0, "currency": "USD"},
            "evidence": evidence,
        },
        "line_items": [],
        "validation": {"needs_review": False, "checks": []},
        "created_at": "2026-04-26T00:00:00Z",
    }

    report = validate_extraction_payload("receipt", payload)

    assert report.needs_review
    assert any(
        check["code"] == "receipt.total_arithmetic" and check["status"] == "failed"
        for check in report.checks
    )


def test_semantic_region_validation_does_not_require_full_canonical_receipt() -> None:
    report = validate_semantic_region_payload(
        {
            "schema_name": "receipt",
            "schema_version": "v1",
            "document_id": str(uuid4()),
            "line_items": [
                {
                    "description": "Coffee",
                    "amount": {"amount": 4.25, "currency": "USD"},
                    "evidence": [{"page_id": str(uuid4()), "semantic_region_id": str(uuid4())}],
                }
            ],
        },
        model_output_schema_name="granite_receipt_line_items.v1",
        model_output_payload={"line_items": [{"description": "Coffee", "amount": "4.25"}]},
    )

    assert report.needs_review
    assert not any(
        check["code"] == "json_schema" and check["status"] == "failed"
        for check in report.checks
    )
    assert any(
        check["code"] == "region_scope.validation_routing" and check["status"] == "passed"
        for check in report.checks
    )
    assert any(
        check["code"] == "region_scope.model_output_contract" and check["status"] == "passed"
        for check in report.checks
    )


def test_semantic_region_validation_checks_model_output_contract() -> None:
    report = validate_semantic_region_payload(
        {
            "schema_name": "receipt",
            "schema_version": "v1",
            "document_id": str(uuid4()),
            "line_items": [],
        },
        model_output_schema_name="granite_receipt_line_items.v1",
        model_output_payload={
            "line_items": [{"description": "Coffee", "unexpected_field": "schema echo"}]
        },
    )

    assert report.needs_review
    assert any(
        check["code"] == "region_scope.model_output_contract" and check["status"] == "failed"
        for check in report.checks
    )


def test_phase4_invoice_heuristic_prefers_explicit_total_and_valid_party_type() -> None:
    source = _source(
        """
        Seller: Acme Repairs
        Buyer: Structura Household
        Invoice Number: INV-4242
        Issue Date: 2026-04-01
        Due Date: 2026-04-30
        Subtotal: 1000.00
        Tax: 42.15
        Total: 1042.15
        Item: Dishwasher service 1042.15
        """
    )

    payload = invoice_payload(source)
    report = validate_extraction_payload("invoice", payload)

    assert payload["seller"]["display_name"] == "Acme Repairs"
    assert payload["seller"]["party_type"] == "company"
    assert payload["totals"]["total"]["amount"] == 1042.15
    assert not report.needs_review


def test_phase4_evidence_requires_concrete_locator() -> None:
    assert not has_concrete_evidence([{"page_number": 1, "source_engine": "docling"}])
    assert has_concrete_evidence(
        [
            {
                "page_number": 1,
                "source_engine": "docling",
                "source_text": "Total 1042.15",
            }
        ]
    )


def _source(
    text: str,
    *,
    metadata: dict[str, object] | None = None,
) -> ExtractionSourceDocument:
    document_id = uuid4()
    page_id = uuid4()
    return ExtractionSourceDocument(
        document_id=document_id,
        household_id=uuid4(),
        title="Fixture",
        original_filename="fixture.pdf",
        mime_type="application/pdf",
        family="generic",
        subtype=None,
        sensitivity="normal",
        document_date=None,
        counterparty_display=None,
        primary_folder_id=None,
        metadata=metadata or {"phase3": {"parseStatus": "succeeded"}},
        pages=[ParsedPageText(page_id=page_id, page_number=1, text=text)],
        elements=[
            ParsedElementText(
                element_id=uuid4(),
                page_number=1,
                ordinal=1,
                text=text,
                bbox={"l": 10, "t": 20, "r": 400, "b": 120},
            )
        ],
        tables=[],
    )
