from __future__ import annotations

import json
from datetime import date
from typing import Any, cast
from uuid import UUID, uuid4

from lib.extraction.candidate_admission import (
    CANDIDATE_GATE_VERSION,
    CandidateAdmissionContext,
    admit_extraction_candidates,
    persist_candidate_admission_events,
    rejected_candidates_from_payload,
)
from lib.extraction.candidate_admission_fingerprints import (
    line_item_fingerprint,
    observation_fingerprint,
)
from lib.extraction.contract_registry import CONTRACT_REGISTRY_VERSION
from lib.extraction.models import (
    CandidateFact,
    ExtractionRunScope,
    LineItemCandidateFact,
    ObservationCandidateFact,
)


def test_prompt_echo_line_item_is_rejected_and_not_admitted() -> None:
    context = _context()
    candidate = LineItemCandidateFact(
        line_item_type="receipt_item",
        ordinal=1,
        description="Identify and extract the schema of all tables in the image",
        quantity=1.0,
        unit="rows",
        unit_price=1.0,
        gross_amount=1.0,
        net_amount=1.0,
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[candidate],
        observation_candidates=[],
    )

    assert admission.line_item_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_artifact": 1},
    }
    assert admission.events[0].decision == "rejected_artifact"
    assert admission.events[0].reasons == ("prompt_or_schema_echo",)


def test_camel_case_prompt_echo_line_item_is_rejected_and_not_admitted() -> None:
    context = _context()
    candidate = LineItemCandidateFact(
        line_item_type="receipt_item",
        ordinal=1,
        description="ReturnOnlyJsonMatchingTheSchema",
        quantity=1.0,
        unit="rows",
        unit_price=1.0,
        gross_amount=1.0,
        net_amount=1.0,
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[candidate],
        observation_candidates=[],
    )

    assert admission.line_item_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_artifact": 1},
    }
    assert admission.events[0].decision == "rejected_artifact"
    assert admission.events[0].reasons == ("prompt_or_schema_echo",)


def test_prompt_echo_key_field_is_rejected_and_not_admitted() -> None:
    context = _context()
    candidate = CandidateFact(
        field_path="receipt.transaction.total",
        value_type="json",
        value={"ReturnOnlyJsonMatchingTheSchema": "42.00"},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.events[0].decision == "rejected_artifact"
    assert admission.events[0].reasons == ("prompt_or_schema_echo",)


def test_schema_artifact_key_field_is_rejected_and_not_admitted() -> None:
    context = _context()
    candidate = CandidateFact(
        field_path="receipt.transaction.total",
        value_type="json",
        value={"$schema": "receipt.v1", "amount": 4.65},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.events[0].decision == "rejected_artifact"
    assert admission.events[0].reasons == ("prompt_or_schema_echo",)


def test_camel_case_schema_artifact_key_field_is_rejected_and_not_admitted() -> None:
    context = _context()
    candidate = CandidateFact(
        field_path="receipt.transaction.total",
        value_type="json",
        value={"jsonSchema": {"type": "object", "properties": {"amount": {"type": "number"}}}},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.events[0].decision == "rejected_artifact"
    assert admission.events[0].reasons == ("prompt_or_schema_echo",)


def test_acronym_schema_artifact_key_field_is_rejected_and_not_admitted() -> None:
    context = _context()
    candidate = CandidateFact(
        field_path="receipt.transaction.total",
        value_type="json",
        value={"JSONSchema": {"type": "object", "properties": {"amount": {"type": "number"}}}},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.events[0].decision == "rejected_artifact"
    assert admission.events[0].reasons == ("prompt_or_schema_echo",)


def test_compact_schema_artifact_key_field_is_rejected_and_not_admitted() -> None:
    context = _context()
    candidate = CandidateFact(
        field_path="receipt.transaction.total",
        value_type="json",
        value={"jsonschema": {"type": "object", "properties": {"amount": {"type": "number"}}}},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.events[0].decision == "rejected_artifact"
    assert admission.events[0].reasons == ("prompt_or_schema_echo",)


def test_embedded_compact_schema_artifact_value_is_rejected_and_not_admitted() -> None:
    context = _context()
    candidate = CandidateFact(
        field_path="receipt.transaction.total",
        value_type="json",
        value={"format_hint": "responseformat:v1"},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.events[0].decision == "rejected_artifact"
    assert admission.events[0].reasons == ("prompt_or_schema_echo",)


def test_camel_case_schema_artifact_value_is_rejected_and_not_admitted() -> None:
    context = _context()
    candidate = CandidateFact(
        field_path="receipt.transaction.total",
        value_type="json",
        value={"format_hint": "jsonSchema"},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.events[0].decision == "rejected_artifact"
    assert admission.events[0].reasons == ("prompt_or_schema_echo",)


def test_model_backed_candidates_are_admitted_as_review_required() -> None:
    context = _context()
    candidate = CandidateFact(
        field_path="receipt.transaction.total",
        value_type="money",
        value={"amount": 4.65, "currency": "USD"},
        currency="USD",
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert len(admission.field_candidates) == 1
    assert admission.field_candidates[0].status == "needs_review"
    assert admission.events[0].decision == "admitted_review_required"
    assert admission.events[0].candidate_gate_version == CANDIDATE_GATE_VERSION
    assert admission.events[0].contract_registry_version == CONTRACT_REGISTRY_VERSION


def test_non_model_source_engine_alias_still_requires_concrete_candidate_evidence() -> None:
    context = _context(source_engine=" System ")
    candidate = CandidateFact(
        field_path="receipt.transaction.total",
        value_type="money",
        value={"amount": 4.65, "currency": "USD"},
        currency="USD",
        evidence=[],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.events[0].decision == "rejected_missing_evidence"
    assert admission.events[0].reasons == ("missing_concrete_evidence",)


def test_model_source_engine_alias_requires_concrete_evidence() -> None:
    context = _context(source_engine="Granite Vision 3B")
    candidate = CandidateFact(
        field_path="receipt.transaction.total",
        value_type="money",
        value={"amount": 4.65, "currency": "USD"},
        currency="USD",
        evidence=[],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.events[0].decision == "rejected_missing_evidence"
    assert admission.events[0].reasons == ("missing_concrete_evidence",)


def test_qwen_source_engine_candidates_are_rejected_even_with_concrete_evidence() -> None:
    context = _context(source_engine="qwen3_vl_8b")
    field_candidate = CandidateFact(
        field_path="receipt.transaction.total",
        value_type="money",
        value={"amount": 4.65, "currency": "USD"},
        currency="USD",
        evidence=[_evidence(context)],
        status="proposed",
    )
    line_item_candidate = LineItemCandidateFact(
        line_item_type="receipt_item",
        ordinal=1,
        description="Coffee",
        net_amount=4.65,
        currency="USD",
        evidence=[_evidence(context)],
        status="proposed",
    )
    observation_candidate = ObservationCandidateFact(
        observation_family="document_observation",
        field_name="claimed_total",
        value_type="string",
        value="$4.65",
        evidence=[_evidence(context)],
        status="needs_review",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[field_candidate],
        line_item_candidates=[line_item_candidate],
        observation_candidates=[observation_candidate],
    )

    assert admission.field_candidates == []
    assert admission.line_item_candidates == []
    assert admission.observation_candidates == []
    assert admission.summary == {
        "produced": 3,
        "admitted": 0,
        "rejected": 3,
        "rejectionReasons": {"rejected_source_provenance": 3},
    }
    assert {event.reasons for event in admission.events} == {
        ("qwen_semantic_source_cannot_emit_value_candidate",)
    }


def test_blank_observation_field_name_is_rejected_before_insertion() -> None:
    context = _context()
    candidate = ObservationCandidateFact(
        observation_family="document_observation",
        field_name="   ",
        value_type="string",
        value="visible escrow note",
        evidence=[_evidence(context)],
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[],
        observation_candidates=[candidate],
    )

    assert admission.observation_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_field_name",)


def test_normalized_placeholder_observation_field_name_is_rejected_before_insertion() -> None:
    context = _context()
    candidate = ObservationCandidateFact(
        observation_family="document_observation",
        field_name="visible field",
        value_type="string",
        value="printed receipt",
        evidence=[_evidence(context)],
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[],
        observation_candidates=[candidate],
    )

    assert admission.observation_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_field_name",)


def test_compact_placeholder_observation_field_name_is_rejected_before_insertion() -> None:
    context = _context()
    candidate = ObservationCandidateFact(
        observation_family="document_observation",
        field_name="visiblefield",
        value_type="string",
        value="printed receipt",
        evidence=[_evidence(context)],
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[],
        observation_candidates=[candidate],
    )

    assert admission.observation_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_field_name",)


def test_report_placeholder_observation_field_name_is_rejected_before_insertion() -> None:
    context = _context()
    candidate = ObservationCandidateFact(
        observation_family="document_observation",
        field_name="Not provided",
        value_type="string",
        value="printed receipt",
        evidence=[_evidence(context)],
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[],
        observation_candidates=[candidate],
    )

    assert admission.observation_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_field_name",)


def test_nested_placeholder_field_value_is_rejected_before_insertion() -> None:
    context = _context()
    candidate = CandidateFact(
        field_path="receipt.transaction.total",
        value_type="money",
        value={"amount": "null", "currency": "USD"},
        currency="USD",
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_or_null_value",)


def test_camel_case_placeholder_field_value_is_rejected_before_insertion() -> None:
    context = _context()
    candidate = CandidateFact(
        field_path="receipt.merchant.display_name",
        value_type="json",
        value={"displayName": "Unknown"},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_or_null_value",)


def test_camel_case_placeholder_token_value_is_rejected_before_insertion() -> None:
    context = _context()
    candidate = CandidateFact(
        field_path="receipt.merchant.display_name",
        value_type="json",
        value={"displayName": "NotProvided"},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_or_null_value",)


def test_compact_placeholder_key_field_value_is_rejected_before_insertion() -> None:
    context = _context()
    candidate = CandidateFact(
        field_path="receipt.merchant.display_name",
        value_type="json",
        value={"displayname": "Unknown"},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_or_null_value",)


def test_compound_name_placeholder_key_field_value_is_rejected_before_insertion() -> None:
    context = _context(canonical_target_schema="invoice")
    candidate = CandidateFact(
        field_path="invoice.seller.display_name",
        value_type="json",
        value={"seller_name": "Unknown"},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_or_null_value",)


def test_compact_compound_name_placeholder_key_field_value_is_rejected_before_insertion() -> None:
    context = _context(canonical_target_schema="invoice")
    candidate = CandidateFact(
        field_path="invoice.seller.display_name",
        value_type="json",
        value={"sellername": "Unknown"},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_or_null_value",)


def test_compound_amount_placeholder_key_field_value_is_rejected_before_insertion() -> None:
    context = _context(canonical_target_schema="invoice")
    candidate = CandidateFact(
        field_path="invoice.total_amount",
        value_type="json",
        value={"total_amount": "Unknown"},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_or_null_value",)


def test_compact_compound_amount_placeholder_key_field_value_is_rejected_before_insertion() -> None:
    context = _context(canonical_target_schema="invoice")
    candidate = CandidateFact(
        field_path="invoice.balance_due",
        value_type="json",
        value={"balancedue": "NotProvided"},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_or_null_value",)


def test_identifier_placeholder_key_field_value_is_rejected_before_insertion() -> None:
    context = _context(canonical_target_schema="invoice")
    candidate = CandidateFact(
        field_path="invoice.invoice_number",
        value_type="json",
        value={"invoice_number": "Unknown"},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_or_null_value",)


def test_compact_date_placeholder_key_field_value_is_rejected_before_insertion() -> None:
    context = _context(canonical_target_schema="receipt")
    candidate = CandidateFact(
        field_path="receipt.transaction.date_local",
        value_type="json",
        value={"transactiondate": "NotProvided"},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_or_null_value",)


def test_address_placeholder_key_field_value_is_rejected_before_insertion() -> None:
    context = _context(canonical_target_schema="invoice")
    candidate = CandidateFact(
        field_path="invoice.seller.display_name",
        value_type="json",
        value={"property_address": "Unknown"},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_or_null_value",)


def test_contract_alias_identifier_placeholder_key_field_value_is_rejected_before_insertion() -> (
    None
):
    context = _context(canonical_target_schema="invoice")
    candidate = CandidateFact(
        field_path="invoice.invoice_number",
        value_type="json",
        value={"invoice_no": "Unknown"},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_or_null_value",)


def test_contract_reason_placeholder_key_field_value_is_rejected_before_insertion() -> None:
    context = _context(canonical_target_schema="receipt")
    candidate = CandidateFact(
        field_path="receipt.dispute_reason",
        value_type="json",
        value={"dispute_reason": "NotProvided"},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_or_null_value",)


def test_contract_payment_placeholder_key_field_value_is_rejected_before_insertion() -> None:
    context = _context(canonical_target_schema="invoice")
    candidate = CandidateFact(
        field_path="invoice.total_amount",
        value_type="json",
        value={"paymentamount": "Unknown"},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_or_null_value",)


def test_repeated_separator_placeholder_field_value_is_rejected_before_insertion() -> None:
    context = _context()
    candidate = CandidateFact(
        field_path="receipt.merchant.display_name",
        value_type="json",
        value={"display__name": "Unknown"},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_or_null_value",)


def test_title_derived_seller_field_is_rejected_before_insertion() -> None:
    context = _context(canonical_target_schema="invoice")
    candidate = CandidateFact(
        field_path="invoice.seller.display_name",
        value_type="string",
        value="Acme Services",
        evidence=[_title_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_source_provenance": 1},
    }
    assert admission.events[0].decision == "rejected_source_provenance"
    assert admission.events[0].reasons == ("title_derived_merchant_seller_without_allowlist",)


def test_title_derived_seller_field_can_be_explicitly_allowlisted() -> None:
    context = _context(
        canonical_target_schema="invoice",
        run_metadata={"allow_title_derived_merchant_seller": True},
    )
    candidate = CandidateFact(
        field_path="invoice.seller.display_name",
        value_type="string",
        value="Acme Services",
        evidence=[_title_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert len(admission.field_candidates) == 1
    assert admission.field_candidates[0].status == "needs_review"
    assert admission.events[0].decision == "admitted_review_required"


def test_report_placeholder_value_is_rejected_before_insertion() -> None:
    context = _context()
    candidate = CandidateFact(
        field_path="receipt.merchant.display_name",
        value_type="json",
        value={"display_name": "Not provided"},
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_or_null_value",)


def test_nested_placeholder_observation_value_is_rejected_before_insertion() -> None:
    context = _context()
    candidate = ObservationCandidateFact(
        observation_family="document_observation",
        field_name="payment_summary",
        value_type="json",
        value={"amount": "null", "currency": "USD"},
        evidence=[_evidence(context)],
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[],
        observation_candidates=[candidate],
    )

    assert admission.observation_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_or_null_value",)


def test_placeholder_line_item_amount_is_rejected_before_insertion() -> None:
    context = _context()
    candidate = LineItemCandidateFact(
        line_item_type="service_line",
        ordinal=1,
        description="Headlight adjustment service",
        service_date=date(2023, 4, 25),
        net_amount=cast(Any, "null"),
        currency="USD",
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[candidate],
        observation_candidates=[],
    )

    assert admission.line_item_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_or_null_value",)


def test_placeholder_line_item_unit_is_rejected_before_insertion() -> None:
    context = _context()
    candidate = LineItemCandidateFact(
        line_item_type="service_line",
        ordinal=1,
        description="Headlight adjustment service",
        service_date=date(2023, 4, 25),
        unit="unknown",
        net_amount=0.0,
        currency="USD",
        category_hint="service",
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[candidate],
        observation_candidates=[],
    )

    assert admission.line_item_candidates == []
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_placeholder": 1},
    }
    assert admission.events[0].decision == "rejected_placeholder"
    assert admission.events[0].reasons == ("placeholder_or_null_value",)


def test_incompatible_field_schema_candidate_is_rejected_before_insertion() -> None:
    context = _context(canonical_target_schema="invoice")
    candidate = CandidateFact(
        field_path="receipt.transaction.total",
        value_type="money",
        value={"amount": 4.65, "currency": "USD"},
        currency="USD",
        evidence=[_evidence(context)],
        status="proposed",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert admission.field_candidates == []
    assert admission.events[0].decision == "rejected_family_schema"
    assert admission.events[0].reasons == ("candidate_schema_incompatible",)


def test_admitted_candidates_carry_admission_fingerprints_for_report_evidence() -> None:
    context = _context()

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[
            CandidateFact(
                field_path="receipt.transaction.total",
                value_type="money",
                value={"amount": 4.65, "currency": "USD"},
                currency="USD",
                evidence=[_evidence(context)],
                status="proposed",
            )
        ],
        line_item_candidates=[
            LineItemCandidateFact(
                line_item_type="receipt_item",
                ordinal=1,
                description="Coffee",
                net_amount=4.65,
                currency="USD",
                evidence=[_evidence(context)],
                status="proposed",
            )
        ],
        observation_candidates=[
            ObservationCandidateFact(
                observation_family="receipt",
                field_name="register_note",
                value_type="string",
                value="printed receipt",
                evidence=[_evidence(context)],
            )
        ],
    )

    assert admission.field_candidates[0].validation["candidateAdmissionFingerprint"] == (
        admission.events[0].candidate_fingerprint
    )
    assert admission.line_item_candidates[0].validation["candidateAdmissionFingerprint"] == (
        admission.events[1].candidate_fingerprint
    )
    assert admission.observation_candidates[0].metadata["candidateAdmissionFingerprint"] == (
        admission.events[2].candidate_fingerprint
    )


def test_observation_admission_fingerprint_includes_semantic_type() -> None:
    semantic_region_id = uuid4()
    payment_context = _context(
        semantic_region_id=semantic_region_id,
        semantic_type="receipt_payment_summary",
    )
    merchant_context = _context(
        semantic_region_id=semantic_region_id,
        semantic_type="merchant_information_block",
    )
    candidate = ObservationCandidateFact(
        observation_family="receipt",
        field_name="visible_note",
        value_type="string",
        value="counter service",
        evidence=[_evidence(payment_context)],
    )

    assert observation_fingerprint(candidate, payment_context) != observation_fingerprint(
        candidate, merchant_context
    )


def test_candidate_fingerprint_ignores_volatile_evidence_ids() -> None:
    first_context = _context(
        semantic_region_id=uuid4(),
        semantic_type="receipt_payment_summary",
    )
    second_context = _context(
        semantic_region_id=uuid4(),
        semantic_type="receipt_payment_summary",
    )
    first_candidate = CandidateFact(
        field_path="receipt.transaction.total",
        value_type="money",
        value={
            "amount": 120.32,
            "currency": "USD",
            "evidence": [
                {
                    "document_id": str(first_context.document_id),
                    "page_id": str(uuid4()),
                    "semantic_region_id": str(first_context.semantic_region_id),
                    "table_id": str(uuid4()),
                }
            ],
        },
        currency="USD",
        evidence=[
            {
                "page_number": 1,
                "page_id": str(uuid4()),
                "semantic_region_id": str(first_context.semantic_region_id),
                "table_id": str(uuid4()),
            }
        ],
        status="proposed",
    )
    second_candidate = CandidateFact(
        field_path="receipt.transaction.total",
        value_type="money",
        value={
            "amount": 120.32,
            "currency": "USD",
            "evidence": [
                {
                    "document_id": str(second_context.document_id),
                    "page_id": str(uuid4()),
                    "semantic_region_id": str(second_context.semantic_region_id),
                    "table_id": str(uuid4()),
                }
            ],
        },
        currency="USD",
        evidence=[
            {
                "page_number": 1,
                "page_id": str(uuid4()),
                "semantic_region_id": str(second_context.semantic_region_id),
                "table_id": str(uuid4()),
            }
        ],
        status="proposed",
    )

    first = admit_extraction_candidates(
        context=first_context,
        field_candidates=[first_candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )
    second = admit_extraction_candidates(
        context=second_context,
        field_candidates=[second_candidate],
        line_item_candidates=[],
        observation_candidates=[],
    )

    assert first.events[0].candidate_fingerprint == second.events[0].candidate_fingerprint


def test_line_item_admission_fingerprint_includes_discount() -> None:
    context = _context(semantic_type="receipt_line_item_table")
    base = {
        "line_item_type": "receipt_item",
        "ordinal": 1,
        "description": "Coffee beans",
        "quantity": 2.0,
        "unit": "bag",
        "unit_price": 12.0,
        "net_amount": 21.0,
        "currency": "USD",
        "category_hint": "grocery",
        "evidence": [_evidence(context)],
    }

    no_discount = LineItemCandidateFact(**base)
    discounted = LineItemCandidateFact(**base, discount_amount=3.0)

    assert line_item_fingerprint(no_discount, context) != line_item_fingerprint(discounted, context)


def test_missing_evidence_rejections_are_recorded_when_no_candidates_are_admitted() -> None:
    context = _context()

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[],
        observation_candidates=[],
        rejected_candidate_payloads=[
            {
                "candidate_kind": "field",
                "field_path": "receipt.transaction.total",
                "payload": {"value": {"amount": 4.65, "currency": "USD"}},
                "decision": "rejected_missing_evidence",
                "reasons": ["missing_concrete_evidence"],
                "evidence_concrete": False,
            }
        ],
    )

    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_missing_evidence": 1},
    }
    assert admission.events[0].field_path == "receipt.transaction.total"
    assert admission.events[0].payload_json["value"] == {"amount": 4.65, "currency": "USD"}


def test_rejected_payload_evidence_concrete_string_false_stays_false() -> None:
    context = _context()

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[],
        observation_candidates=[],
        rejected_candidate_payloads=[
            {
                "candidate_kind": "field",
                "field_path": "receipt.transaction.total",
                "payload": {"value": {"amount": 4.65, "currency": "USD"}},
                "decision": "rejected_missing_evidence",
                "reasons": ["missing_concrete_evidence"],
                "evidence_concrete": "False",
            }
        ],
    )

    assert admission.events[0].evidence_concrete is False
    assert admission.rejected_candidates[0]["evidenceConcrete"] is False


def test_rejected_payload_decision_is_normalized_for_summary() -> None:
    context = _context()

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[],
        observation_candidates=[],
        rejected_candidate_payloads=[
            {
                "candidate_kind": "field",
                "field_path": "receipt.transaction.total",
                "payload": {"value": {"amount": 4.65, "currency": "USD"}},
                "decision": " Rejected_Missing_Evidence ",
                "reasons": ["missing_concrete_evidence"],
                "evidence_concrete": False,
            }
        ],
    )

    assert admission.events[0].decision == "rejected_missing_evidence"
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_missing_evidence": 1},
    }


def test_rejected_payload_decision_separators_are_normalized_for_summary() -> None:
    context = _context()

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[],
        observation_candidates=[],
        rejected_candidate_payloads=[
            {
                "candidate_kind": "field",
                "field_path": "receipt.transaction.total",
                "payload": {"value": {"amount": 4.65, "currency": "USD"}},
                "decision": " Rejected Missing-Evidence ",
                "reasons": ["missing_concrete_evidence"],
                "evidence_concrete": False,
            }
        ],
    )

    assert admission.events[0].decision == "rejected_missing_evidence"
    assert admission.summary == {
        "produced": 1,
        "admitted": 0,
        "rejected": 1,
        "rejectionReasons": {"rejected_missing_evidence": 1},
    }


def test_rejected_payload_candidate_kind_is_normalized_for_event() -> None:
    context = _context()

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[],
        observation_candidates=[],
        rejected_candidate_payloads=[
            {
                "candidate_kind": " LineItem ",
                "field_path": None,
                "payload": {
                    "description": "Front tire service",
                    "net_amount": {"amount": 145.0, "currency": "USD"},
                },
                "decision": "rejected_missing_evidence",
                "reasons": ["missing_concrete_evidence"],
                "evidence_concrete": False,
            }
        ],
    )

    assert admission.events[0].candidate_kind == "line_item"
    assert admission.rejected_candidates[0]["candidateKind"] == "line_item"


def test_rejected_payload_field_path_is_trimmed_for_event() -> None:
    context = _context()

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[],
        observation_candidates=[],
        rejected_candidate_payloads=[
            {
                "candidate_kind": "field",
                "field_path": " receipt.transaction.total ",
                "payload": {"value": {"amount": 4.65, "currency": "USD"}},
                "decision": "rejected_missing_evidence",
                "reasons": ["missing_concrete_evidence"],
                "evidence_concrete": False,
            }
        ],
    )

    assert admission.events[0].field_path == "receipt.transaction.total"
    assert admission.rejected_candidates[0]["fieldPath"] == "receipt.transaction.total"


def test_rejected_payload_string_reason_stays_whole() -> None:
    context = _context()

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[],
        observation_candidates=[],
        rejected_candidate_payloads=[
            {
                "candidate_kind": "field",
                "field_path": "receipt.transaction.total",
                "payload": {"value": {"amount": 4.65, "currency": "USD"}},
                "decision": "rejected_missing_evidence",
                "reasons": "missing_concrete_evidence",
                "evidence_concrete": False,
            }
        ],
    )

    assert admission.events[0].reasons == ("missing_concrete_evidence",)
    assert admission.rejected_candidates[0]["reasons"] == ["missing_concrete_evidence"]


def test_rejected_payload_reason_tokens_are_normalized() -> None:
    context = _context()

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[],
        observation_candidates=[],
        rejected_candidate_payloads=[
            {
                "candidate_kind": "field",
                "field_path": "receipt.transaction.total",
                "payload": {"value": {"amount": 4.65, "currency": "USD"}},
                "decision": "rejected_missing_evidence",
                "reasons": [" Missing Concrete-Evidence ", "", None],
                "evidence_concrete": False,
            }
        ],
    )

    assert admission.events[0].reasons == ("missing_concrete_evidence",)
    assert admission.rejected_candidates[0]["reasons"] == ["missing_concrete_evidence"]


def test_payload_rejection_scan_records_candidates_dropped_before_admission() -> None:
    context = _context()

    rejected = rejected_candidates_from_payload(
        schema_name="receipt",
        payload={
            "line_items": [
                {
                    "description": "Identify and extract the schema",
                    "quantity": "1.0000",
                    "unit": "rows",
                    "amount": {"amount": 1.0, "currency": "USD"},
                    "evidence": [_evidence(context)],
                }
            ]
        },
        context=context,
        require_concrete_evidence=True,
    )

    assert rejected == [
        {
            "candidate_kind": "line_item",
            "field_path": None,
            "payload": {
                "description": "Identify and extract the schema",
                "quantity": "1.0000",
                "unit": "rows",
                "amount": {"amount": 1.0, "currency": "USD"},
                "evidence": [_evidence(context)],
            },
            "decision": "rejected_artifact",
            "reasons": ["prompt_or_schema_echo"],
            "evidence_concrete": True,
        }
    ]


def test_duplicate_candidates_are_rejected_before_insertion() -> None:
    context = _context()
    evidence = [_evidence(context)]
    first = LineItemCandidateFact(
        line_item_type="receipt_item",
        ordinal=1,
        description="Pellegrino Sparkler 16oz Bottle",
        gross_amount=5.0,
        net_amount=5.0,
        currency="USD",
        evidence=evidence,
        status="needs_review",
    )
    duplicate = LineItemCandidateFact(
        line_item_type="receipt_item",
        ordinal=2,
        description="  pellegrino sparkler 16oz bottle  ",
        gross_amount=5.0,
        net_amount=5.0,
        currency="USD",
        evidence=evidence,
        status="needs_review",
    )

    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[],
        line_item_candidates=[first, duplicate],
        observation_candidates=[],
    )

    assert [candidate.description for candidate in admission.line_item_candidates] == [
        "Pellegrino Sparkler 16oz Bottle"
    ]
    assert [event.decision for event in admission.events] == [
        "admitted_review_required",
        "rejected_duplicate",
    ]


def test_admission_events_insert_with_lineage_and_version_fields() -> None:
    context = _context()
    extraction_id = uuid4()
    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[
            CandidateFact(
                field_path="receipt.merchant.display_name",
                value_type="string",
                value="Coffee Shop",
                evidence=[_evidence(context)],
                status="needs_review",
            )
        ],
        line_item_candidates=[],
        observation_candidates=[],
    )
    cursor = RecordingCursor()

    persist_candidate_admission_events(
        cursor,
        extraction_id=extraction_id,
        events=admission.events,
    )

    sql, params = cursor.queries[0]
    assert "INSERT INTO candidate_admission_events" in sql
    assert context.plan_id in params
    assert context.plan_task_id in params
    assert context.semantic_annotation_id in params
    assert context.region_envelope_version in params
    assert CANDIDATE_GATE_VERSION in params
    assert CONTRACT_REGISTRY_VERSION in params


def test_admission_event_payloads_are_json_serializable_with_candidate_dates() -> None:
    context = _context()
    extraction_id = uuid4()
    admission = admit_extraction_candidates(
        context=context,
        field_candidates=[
            CandidateFact(
                field_path="receipt.transaction.date_local",
                value_type="date",
                value=date(2026, 5, 2),
                evidence=[_evidence(context)],
                status="needs_review",
            )
        ],
        line_item_candidates=[
            LineItemCandidateFact(
                line_item_type="service_line",
                ordinal=1,
                description="Scheduled service inspection",
                service_date=date(2026, 5, 2),
                net_amount=0.0,
                currency="USD",
                category_hint="service",
                evidence=[_evidence(context)],
                status="needs_review",
            )
        ],
        observation_candidates=[],
    )
    cursor = JsonSerializingCursor()

    persist_candidate_admission_events(
        cursor,
        extraction_id=extraction_id,
        events=admission.events,
    )

    assert [payload["value"] for payload in cursor.payloads if "value" in payload] == ["2026-05-02"]
    service_dates = [
        payload["service_date"] for payload in cursor.payloads if "service_date" in payload
    ]
    assert service_dates == ["2026-05-02"]


class RecordingCursor:
    def __init__(self) -> None:
        self.queries: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.queries.append((sql, params))


class JsonSerializingCursor(RecordingCursor):
    def __init__(self) -> None:
        super().__init__()
        self.payloads: list[dict[str, object]] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        super().execute(sql, params)
        jsonb_payload = cast(Any, params[-1])
        serialized = json.dumps(jsonb_payload.obj)
        self.payloads.append(json.loads(serialized))


def _context(
    *,
    canonical_target_schema: str = "receipt",
    source_engine: str = "granite_vision_3b",
    semantic_region_id: UUID | None = None,
    semantic_type: str = "receipt_payment_summary",
    run_metadata: dict[str, Any] | None = None,
) -> CandidateAdmissionContext:
    return CandidateAdmissionContext(
        document_id=uuid4(),
        run_scope=ExtractionRunScope.semantic_region(
            semantic_annotation_id=uuid4(),
            source_semantic_region_id=semantic_region_id or uuid4(),
            semantic_type=semantic_type,
            granite_task="kvp",
            plan_id=uuid4(),
            plan_task_id=uuid4(),
            canonical_target_schema=canonical_target_schema,
            compatibility_mode="exact",
            contract_resolution_reason="exact_contract",
            region_envelope_version="phase8_5-region-envelope-v1",
            metadata=run_metadata,
        ),
        source_engine=source_engine,
        model_output_schema_name="granite_receipt_payment_summary.v1",
    )


def _evidence(context: CandidateAdmissionContext) -> dict[str, object]:
    return {
        "document_id": str(context.document_id),
        "semantic_annotation_id": str(context.semantic_annotation_id),
        "semantic_region_id": str(context.semantic_region_id),
        "page_number": 1,
        "source_engine": context.source_engine,
        "source_text": "Coffee Shop total $4.65",
    }


def _title_evidence(context: CandidateAdmissionContext) -> dict[str, object]:
    return {
        "document_id": str(context.document_id),
        "semantic_annotation_id": str(context.semantic_annotation_id),
        "semantic_region_id": str(context.semantic_region_id),
        "page_number": 1,
        "sourceEngine": "DocumentTitle",
        "source_text": "Acme Services Invoice 1001",
        "text_span": {"start": 0, "end": 13, "basis": "document_title"},
    }
