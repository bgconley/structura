"""Adversarial diagnostic accounting, independent from model and source quality claims."""

from copy import deepcopy

import pytest

from lib.document_parsing.page_understanding.model import PageUnderstanding
from scripts.gpu.page_understanding_probe.scoring import score_page, value_identity
from tests.fixtures.page_understanding_sources import invoice_page


def expected():
    line = [
        {
            "canonical_key": "invoice.line_item.description",
            "value_type": "text",
            "typed_value": "Service",
        },
        {
            "canonical_key": "invoice.line_item.amount",
            "value_type": "money",
            "typed_value": {"amount": "12.34", "currency": "USD"},
        },
    ]
    return {
        "page_number": 1,
        "family": "invoice",
        "fields": [
            {
                "canonical_key": "invoice.invoice_number",
                "value_type": "identifier",
                "typed_value": "000123",
            }
        ],
        "rows": [
            {"source_row": 1, "claims": deepcopy(line)},
            {"source_row": 2, "claims": deepcopy(line)},
        ],
    }


def test_exact_repeated_occurrences_and_physical_groups_are_counted():
    page = PageUnderstanding.model_validate(invoice_page())
    report = score_page(page, expected())
    assert report["classification"]["exact_primary_family"] is True
    assert report["annotated_scalar_values"]["recall"] == 1
    assert report["annotated_line_values"]["matched_occurrences"] == 4
    assert report["physical_row_grouping"]["matched_occurrences"] == 2
    assert report["model_reported_ledger"]["annotated_scalar_keys_reported_present"] == 1
    assert report["overall_precision"] == "not_evaluated"


def test_dropped_repeated_row_cannot_match_two_source_occurrences():
    page = PageUnderstanding.model_validate(invoice_page())
    # Scorer-only fault injection. Live capture first passes the strict decoder.
    page = page.model_copy(
        update={
            "extraction": page.extraction.model_copy(update={"claims": page.extraction.claims[:3]})
        }
    )
    report = score_page(page, expected())
    assert report["annotated_line_values"]["matched_occurrences"] == 2
    assert report["physical_row_grouping"]["matched_occurrences"] == 1
    assert report["physical_row_grouping"]["missing_occurrences"] == 1


def test_correct_values_on_wrong_row_groups_do_not_pass_grouping():
    page = PageUnderstanding.model_validate(invoice_page())
    claims = list(page.extraction.claims)
    claims[2] = claims[2].model_copy(update={"physical_row": claims[4].physical_row})
    altered = page.model_copy(
        update={"extraction": page.extraction.model_copy(update={"claims": tuple(claims)})}
    )
    report = score_page(altered, expected())
    assert report["annotated_line_values"]["recall"] == 1
    assert report["physical_row_grouping"]["matched_occurrences"] == 0


def test_zero_values_do_not_pass_on_model_reported_complete_or_present_ledgers():
    page = PageUnderstanding.model_validate(invoice_page())
    altered = page.model_copy(
        update={"extraction": page.extraction.model_copy(update={"claims": ()})}
    )
    report = score_page(altered, expected())
    assert report["model_reported_ledger"]["disposition"] == "complete"
    assert report["annotated_scalar_values"]["recall"] == 0
    assert report["annotated_line_values"]["recall"] == 0
    assert report["physical_row_grouping"]["recall"] == 0


def test_extra_claims_are_unscored_without_asserting_false_positive():
    page = PageUnderstanding.model_validate(invoice_page())
    gold = expected()
    gold["fields"] = []
    report = score_page(page, gold)
    assert report["unscored_extra_claim_count"] == 1
    assert report["unscored_extra_claims"][0]["typed_value"] == "000123"
    assert report["overall_precision"] == "not_evaluated"
    assert report["full_business_coverage"] == "not_evaluated"


def test_decimal_scale_equal_without_context_rounding_or_identifier_loss():
    def identity(value, kind="quantity"):
        return value_identity({"canonical_key": "test", "value_type": kind, "typed_value": value})

    assert identity("12.3400") == identity("12.34")
    assert identity("-0.00") == identity("0")
    assert identity("12345678901234567890123456789012345678") != identity(
        "12345678901234567890123456789012345679"
    )
    assert identity("000123", "identifier") != identity("123", "identifier")
    assert identity("-5.25") != identity("5.25")


def test_page_identity_is_mandatory():
    gold = expected()
    gold["page_number"] = 2
    with pytest.raises(ValueError, match="page"):
        score_page(PageUnderstanding.model_validate(invoice_page()), gold)
