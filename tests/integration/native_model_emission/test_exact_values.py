import pytest

from lib.auth.request_authority import RequestCredential
from lib.db.connection import db_connection
from lib.extraction.native_claims.model_emission.service import NativeModelEmissionService
from tests.fixtures.native_model_emission_values import eob_modifier_page, single_field_page
from tests.integration.native_model_emission.conftest import populated, setup_source


@pytest.mark.parametrize("kind", ["time", "identifiers", "money", "date"])
def test_native_exact_value_branches_survive_json_sql_and_retained_rebuild(processing, kind):
    if kind == "identifiers":
        output, expected = eob_modifier_page(), ["025", "59"]
    elif kind == "time":
        expected = "07:04:03"
        output = single_field_page("receipt", "transaction.time_local", kind, expected, expected)
    elif kind == "money":
        expected = {"amount": "9007199254740.1234", "currency": "USD"}
        output = single_field_page("invoice", "total_amount", kind, "$9007199254740.1234", expected)
    else:
        expected = "2026-09-07"
        output = single_field_page("invoice", "issue_date", kind, "09/07/2026", expected)
    harness, _, _, binding, _ = populated(setup_source(processing, [output]))
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT typed_value_json,value_type,native_payload_json FROM extraction_claims "
            "WHERE native_claim_set_id=%s",
            (binding.claim_set_id,),
        )
        rows = cur.fetchall()
    assert len(rows) == 1 and rows[0]["value_type"] == kind
    assert rows[0]["typed_value_json"] == expected
    assert rows[0]["native_payload_json"]["requires_review"] is True
    assert rows[0]["native_payload_json"]["source_pixel_support"] == "not_evaluated"
    if kind in {"money", "date"}:
        assert rows[0]["native_payload_json"]["interpretation_diagnostics"]
    projection = NativeModelEmissionService().rebuild(
        binding, credential=RequestCredential.from_principal(harness.principal)
    )
    assert projection["claims_are_accepted_facts"] is False
