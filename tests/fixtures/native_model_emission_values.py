"""Independent exact value/obligation examples shared by unit and persisted SQL tests."""

from tests.fixtures.page_understanding_sources import invoice_page, locator, prose_page


def single_field_page(family, key, kind, printed, value):
    output = prose_page(family, unsupported=False)
    output["elements"][0]["text"] = printed
    output["classification"]["alternatives"][0]["evidence"] = [
        {"quote": printed, "locator": locator(0, printed)}
    ]
    output["extraction"].update(
        {
            "disposition": "complete",
            "reasons": [],
            "claims": [
                {
                    "canonical_key": f"{family}.{key}",
                    "value_type": kind,
                    "typed_value": value,
                    "raw_value": printed,
                    "primary_source": locator(0, printed),
                    "physical_row": None,
                    "supporting_sources": [],
                    "uncalibrated_score": None,
                }
            ],
        }
    )
    next(
        f
        for f in output["extraction"]["families"][0]["fields"]
        if f["canonical_key"] == f"{family}.{key}"
    ).update({"state": "present", "claim_indices": [0]})
    return output


def eob_modifier_page():
    from tests.fixtures.page_understanding_sources import EOB_FIELDS, statuses

    output = invoice_page()
    output["classification"]["primary_family"] = "medical_eob"
    output["classification"]["alternatives"][0]["family"] = "medical_eob"
    output["elements"][1]["table"]["cells"][2]["text"] = "025, 59"
    line_keys = (
        "description",
        "service_date",
        "service_end_date",
        "code",
        "modifiers",
        "diagnosis_code",
        "revenue_code",
        "place_of_service",
        "quantity",
        "gross_amount",
        "allowed_amount",
        "plan_paid",
        "amount",
        "deductible",
        "copay",
        "coinsurance",
        "category_hint",
        "remark_codes",
    )
    physical = {"kind": "table_row", "element_index": 1, "row": 1}
    output["extraction"]["claims"] = [
        {
            "canonical_key": "medical_eob.line_item.modifiers",
            "value_type": "identifiers",
            "typed_value": ["025", "59"],
            "raw_value": "025, 59",
            "primary_source": locator(1, "025, 59", row=1, column=0),
            "physical_row": physical,
            "supporting_sources": [],
            "uncalibrated_score": None,
        }
    ]
    output["extraction"]["families"] = [
        {
            "family": "medical_eob",
            "fields": statuses("medical_eob.", EOB_FIELDS),
            "rows": [
                {
                    "physical_row": physical,
                    "fields": statuses("medical_eob.line_item.", line_keys, {"modifiers": [0]}),
                }
            ],
            "excluded_rows": [
                {
                    "physical_row": {"kind": "table_row", "element_index": 1, "row": n},
                    "reason": "not_a_line_item",
                }
                for n in (0, 2)
            ],
            "row_inventory": "complete",
        }
    ]
    return output
