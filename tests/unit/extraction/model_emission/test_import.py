import json
from copy import deepcopy
from dataclasses import replace

import pytest
from pydantic import ValidationError

from lib.document_parsing.page_understanding.codec import canonical_digest
from lib.document_processing.errors import ProcessingError
from lib.extraction.native_claims.errors import NativeClaimError
from lib.extraction.native_claims.model_emission.configuration import installed_configuration
from lib.extraction.native_claims.model_emission.import_page import import_checkpoint
from lib.extraction.native_claims.model_emission.models import NativeModelClaim
from lib.extraction.native_claims.model_emission.projection import diagnostic_projection
from tests.fixtures.native_model_emission_source import digest, source
from tests.fixtures.native_model_emission_values import eob_modifier_page, single_field_page
from tests.fixtures.page_understanding_sources import invoice_page, locator, prose_page


def imported(output=None):
    binding, parse, inventory, checkpoint = source(output)
    return import_checkpoint(
        binding, installed_configuration(), parse, inventory, checkpoint, digest(checkpoint)
    )


def test_exact_raw_members_distinct_rows_and_review_only_projection():
    page, claims = imported()
    assert len(claims) == 5 and len({c.claim_id for c in claims}) == 5
    assert claims[2].proposed.typed_value.amount == "12.3400"
    assert claims[2].group_id != claims[4].group_id
    assert claims[0].proposed.typed_value == "000123"
    assert [c.member.index for c in claims] == list(range(5))
    for c in claims:
        assert c.member.canonical_member_sha256 == canonical_digest(c.raw_member_json)
        assert NativeModelClaim.model_validate_json(c.model_dump_json()) == c
    result = diagnostic_projection(claims, (page,))
    assert result["claims_are_accepted_facts"] is False
    assert result["document_required_key_evaluation"] == "not_evaluated"
    assert len(result["line_rows"]) == 2


@pytest.mark.parametrize("change", ["raw", "digest", "config", "invocation", "source", "engine"])
def test_source_and_request_substitution_cannot_create_native_claims(change):
    binding, parse, inventory, checkpoint = source()
    expected = digest(checkpoint)
    if change == "raw":
        checkpoint = replace(checkpoint, raw_output=checkpoint.raw_output + " ")
    elif change == "digest":
        expected = "0" * 64
    elif change == "config":
        parse = parse.model_copy(update={"prompt_version": "another-prompt"})
    elif change == "invocation":
        checkpoint = replace(
            checkpoint,
            invocation=checkpoint.invocation.model_copy(update={"request_sha256": "0" * 64}),
        )
    elif change == "engine":
        parse = parse.model_copy(update={"source_engine": "docling"})
        checkpoint = replace(
            checkpoint,
            invocation=checkpoint.invocation.model_copy(update={"source_engine": "docling"}),
        )
    else:
        inventory = inventory.model_copy(update={"original_sha256": "0" * 64})
    if change in {"raw", "invocation", "engine"}:
        expected = digest(
            checkpoint
        )  # Even a recomputed envelope hash cannot forge request binding.
    with pytest.raises((ValueError, NativeClaimError, ProcessingError)):
        import_checkpoint(
            binding, installed_configuration(), parse, inventory, checkpoint, expected
        )


@pytest.mark.parametrize("field", ["claim_id", "member", "typed_value", "source_quote", "support"])
def test_retained_claim_cannot_silently_change_its_original_member(field):
    _, claims = imported()
    payload = claims[2].model_dump(mode="json")
    if field == "claim_id":
        payload["claim_id"] = "0" * 64
    elif field == "member":
        payload["member"]["index"] = 99
    elif field == "typed_value":
        payload["proposed"]["typed_value"]["amount"] = "99.00"
    elif field == "source_quote":
        payload["anchor"]["source_text"] = "USD 99.0000"
    else:
        payload["supporting_anchors"] = [{"role": "currency", "anchor": payload["anchor"]}]
    with pytest.raises(ValidationError):
        NativeModelClaim.model_validate(payload)


@pytest.mark.parametrize("family", ["receipt", "invoice", "medical_eob", "legal_notice"])
def test_zero_claim_page_preserves_classification_and_explicit_ledger(family):
    page, claims = imported(prose_page(family, unsupported=family == "legal_notice"))
    assert claims == () and page.members == ()
    assert page.classification_json["primary_family"] == family
    assert page.bound_evidence[0].anchor.source_text
    if family != "legal_notice":
        assert page.coverage_json["families"][0]["fields"]


def test_repeated_scalar_occurrences_are_not_collapsed_by_old_105_identity():
    output = invoice_page()
    output["elements"][0]["text"] = "Invoice 000123 000123"
    repeat = deepcopy(output["extraction"]["claims"][0])
    repeat["primary_source"] = locator(0, "000123", start=15)
    output["extraction"]["claims"].append(repeat)
    next(
        f
        for f in output["extraction"]["families"][0]["fields"]
        if f["canonical_key"] == "invoice.invoice_number"
    )["claim_indices"].append(5)
    _, claims = imported(output)
    assert claims[0].claim_id != claims[5].claim_id
    assert claims[0].physical_source_id != claims[5].physical_source_id


def test_import_replay_is_exact_and_calls_no_provider():
    binding, parse, inventory, checkpoint = source()
    config = installed_configuration()
    first = import_checkpoint(binding, config, parse, inventory, checkpoint, digest(checkpoint))
    second = import_checkpoint(binding, config, parse, inventory, checkpoint, digest(checkpoint))
    assert first == second
    assert first[1][0].member.canonical_member_sha256 == canonical_digest(
        json.loads(checkpoint.raw_output)["extraction"]["claims"][0]
    )


@pytest.mark.parametrize(
    "family,key,kind,printed,value,reason",
    [
        ("receipt", "transaction.time_local", "time", "07:04:03", "07:04:03", None),
        ("invoice", "issue_date", "date", "09/07/2026", "2026-09-07", "date_interpretation"),
        (
            "invoice",
            "total_amount",
            "money",
            "$9007199254740.1234",
            {"amount": "9007199254740.1234", "currency": "USD"},
            "ambiguous_currency",
        ),
    ],
)
def test_time_and_interpreted_exact_values_remain_separate_from_source_text(
    family, key, kind, printed, value, reason
):
    output = single_field_page(family, key, kind, printed, value)
    _, claims = imported(output)
    assert claims[0].raw_member_json["typed_value"] == value
    assert claims[0].proposed.raw_value == printed
    if reason:
        assert reason in claims[0].interpretation_diagnostics


def test_member_typing_never_erases_identifier_list_digits():
    output = eob_modifier_page()
    _, claims = imported(output)
    assert claims[0].proposed.typed_value == ("025", "59")
