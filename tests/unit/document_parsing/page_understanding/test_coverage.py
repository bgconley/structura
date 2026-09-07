from copy import deepcopy

import pytest
from pydantic import ValidationError

from lib.document_parsing.page_understanding.interpretation import interpretation_diagnostics
from lib.document_parsing.page_understanding.model import PageUnderstanding
from tests.fixtures.page_understanding_sources import (
    empty_family,
    invoice_page,
    locator,
    prose_page,
    quote,
)


def find_field(page, key):
    return next(f for f in page["extraction"]["families"][0]["fields"] if f["canonical_key"] == key)


@pytest.mark.parametrize(
    "defect",
    [
        "missing_field_obligation",
        "double_accounting",
        "wrong_key",
        "unlisted_claim",
        "skip_row",
        "unreadable_complete",
        "not_applicable_required",
        "unknown_family",
        "wrong_type",
        "lost_identifier_zero",
        "unsupported_as_no_target",
        "bool_claim_index",
    ],
)
def test_complete_cannot_conceal_unaccounted_or_invalid_proposals(defect):
    page = invoice_page()
    extraction = page["extraction"]
    family = extraction["families"][0]
    if defect == "missing_field_obligation":
        family["fields"].pop()
    elif defect == "double_accounting":
        family["fields"][0]["claim_indices"] = [0]
        family["fields"][0]["state"] = "present"
    elif defect == "wrong_key":
        extraction["claims"][0]["canonical_key"] = "receipt.transaction.receipt_number"
    elif defect == "unlisted_claim":
        field = find_field(page, "invoice.invoice_number")
        field["claim_indices"], field["state"] = [], "not_on_this_page"
    elif defect == "skip_row":
        family["excluded_rows"] = []
    elif defect == "unreadable_complete":
        family["fields"][0]["state"] = "unreadable"
    elif defect == "not_applicable_required":
        family["fields"][0]["state"] = "not_applicable"
    elif defect == "unknown_family":
        extraction["claims"][0]["canonical_key"] = "unregistered.number"
    elif defect == "wrong_type":
        extraction["claims"][0]["value_type"] = "text"
    elif defect == "lost_identifier_zero":
        extraction["claims"][0]["typed_value"] = "123"
    elif defect == "unsupported_as_no_target":
        page = prose_page()
        page["extraction"]["disposition"] = "no_extraction_target"
        page["extraction"]["reasons"] = ["no_typed_target"]
    else:
        find_field(page, "invoice.invoice_number")["claim_indices"] = [False]
    with pytest.raises(ValidationError):
        PageUnderstanding.model_validate(page)


def test_explicit_omission_remains_partial_and_retains_every_existing_claim():
    page = invoice_page()
    due = find_field(page, "invoice.due_date")
    due.update({"state": "omitted", "evidence": [quote(0, "Invoice")]})
    with pytest.raises(ValidationError):
        PageUnderstanding.model_validate(page)
    page["extraction"]["disposition"] = "partial"
    page["extraction"]["reasons"] = ["content_omitted"]
    parsed = PageUnderstanding.model_validate(page)
    assert len(parsed.extraction.claims) == 5
    assert (
        next(
            f for f in parsed.extraction.families[0].fields if f.canonical_key == "invoice.due_date"
        ).state
        == "omitted"
    )


def test_model_date_and_currency_interpretations_never_become_verified_literals():
    page = invoice_page()
    page["elements"][0]["text"] = "Invoice 09/07/2026"
    claim = page["extraction"]["claims"][0]
    claim.update(
        {
            "canonical_key": "invoice.issue_date",
            "value_type": "date",
            "typed_value": "2026-09-07",
            "raw_value": "09/07/2026",
            "primary_source": locator(0, "09/07/2026", start=8),
        }
    )
    find_field(page, "invoice.invoice_number").update(
        {"state": "not_on_this_page", "claim_indices": []}
    )
    find_field(page, "invoice.issue_date").update({"state": "present", "claim_indices": [0]})
    page["elements"][1]["table"]["cells"][3]["text"] = "$12.34"
    page["extraction"]["claims"][2].update(
        {"raw_value": "$12.34", "primary_source": locator(1, "$12.34", row=1, column=1)}
    )
    parsed = PageUnderstanding.model_validate(page)
    reports = interpretation_diagnostics(parsed)
    assert "date_interpretation" in reports[0]["reasons"]
    assert "ambiguous_currency" in reports[2]["reasons"]
    assert reports[2]["requires_review"] and reports[2]["source_pixel_support"] == "not_evaluated"
    assert parsed.extraction.claims[0].typed_value == "2026-09-07"
    assert parsed.extraction.claims[0].raw_value == "09/07/2026"


def test_mixed_and_unknown_page_classification_do_not_invent_a_primary_or_calibration():
    page = invoice_page()
    other = deepcopy(page["classification"]["alternatives"][0])
    other["family"], other["uncalibrated_score"] = "legal_notice", 0.9
    page["classification"].update({"outcome": "mixed", "primary_family": None})
    page["classification"]["alternatives"].append(other)
    page["extraction"]["unsupported_families"] = ["legal_notice"]
    page["extraction"].update({"disposition": "partial", "reasons": ["unsupported_family"]})
    parsed = PageUnderstanding.model_validate(page)
    assert parsed.classification.primary_family is None
    assert [a.uncalibrated_score for a in parsed.classification.alternatives] == [0.8, 0.9]


def test_empty_line_inventory_requires_explicit_zero_row_status():
    page = invoice_page()
    page["extraction"]["claims"] = page["extraction"]["claims"][:1]
    family = page["extraction"]["families"][0]
    family["rows"], family["excluded_rows"] = [], []
    with pytest.raises(ValidationError, match="Empty line inventory"):
        PageUnderstanding.model_validate(page)
    family["row_inventory"] = "no_rows_on_this_page"
    with pytest.raises(ValidationError, match="every recorded table row"):
        PageUnderstanding.model_validate(page)
    page["elements"].pop(1)  # A separate header-only source legitimately has no table rows.
    assert PageUnderstanding.model_validate(page).extraction.claims[0].typed_value == "000123"


def test_blank_claim_cannot_discard_recorded_prose():
    page = prose_page("generic", unsupported=False)
    page["classification"] = {
        "outcome": "unknown",
        "primary_family": None,
        "alternatives": [],
        "unknown_reason": "blank_page",
    }
    with pytest.raises(ValidationError, match="Blank-page"):
        PageUnderstanding.model_validate(page)


@pytest.mark.parametrize("family", ["receipt", "invoice", "medical_eob"])
def test_known_typed_boilerplate_requires_complete_explicit_absence_ledger(family):
    page = prose_page(family, unsupported=False)
    parsed = PageUnderstanding.model_validate(page)
    assert parsed.extraction.disposition == "no_extraction_target"
    assert parsed.extraction.families[0].row_inventory == "no_rows_on_this_page"
    assert {f.state for f in parsed.extraction.families[0].fields} == {"not_on_this_page"}
    page["extraction"]["families"] = []
    with pytest.raises(ValidationError, match="full page-local obligation ledger"):
        PageUnderstanding.model_validate(page)


def test_mixed_typed_components_must_each_account_for_their_fields():
    page = invoice_page()
    other = deepcopy(page["classification"]["alternatives"][0])
    other["family"] = "medical_eob"
    page["classification"].update({"outcome": "mixed", "primary_family": None})
    page["classification"]["alternatives"].append(other)
    with pytest.raises(ValidationError, match="full page-local obligation ledger"):
        PageUnderstanding.model_validate(page)
    page["extraction"]["families"].append(empty_family("medical_eob"))
    parsed = PageUnderstanding.model_validate(page)
    assert {f.family for f in parsed.extraction.families} == {"invoice", "medical_eob"}


@pytest.mark.parametrize("unqualified_disposition", ["complete", "no_extraction_target"])
def test_ambiguous_typed_alternatives_remain_partial_even_with_full_page_ledgers(
    unqualified_disposition,
):
    page = prose_page("invoice", unsupported=False)
    other = deepcopy(page["classification"]["alternatives"][0])
    other["family"] = "receipt"
    page["classification"].update({"outcome": "ambiguous", "primary_family": None})
    page["classification"]["alternatives"].append(other)
    page["extraction"].update({"disposition": "partial", "reasons": ["ambiguous_interpretation"]})
    with pytest.raises(ValidationError, match="full page-local obligation ledger"):
        PageUnderstanding.model_validate(page)
    page["extraction"]["families"].append(empty_family("receipt"))
    parsed = PageUnderstanding.model_validate(page)
    assert parsed.extraction.disposition == "partial"
    assert parsed.extraction.claims == ()
    page["extraction"]["disposition"] = unqualified_disposition
    with pytest.raises(ValidationError, match="Ambiguous classification"):
        PageUnderstanding.model_validate(page)
