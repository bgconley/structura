from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

from lib.fact_authority.line_projection import selected_facts_digest
from lib.fact_authority.projection_values import accepted_facts_digest
from lib.review.line_items.source_values import public_evidence, source_snapshot


def sample():
    return {
        "id": uuid4(),
        "document_id": uuid4(),
        "extraction_id": uuid4(),
        "source_engine": "qwen3_8_27b",
        "line_item_type": "service_line",
        "ordinal": 1,
        "net_amount": Decimal("99999999999999.9999"),
        "plan_paid_amount": Decimal("0.0000"),
        "allowed_amount": Decimal("-3.0001"),
        "description": "Recorded service",
        "evidence_json": [
            {
                "pageNumber": 1,
                "sourceEngine": "qwen3_8_27b",
                "sourceText": "Recorded service",
                "uri": "/private/archive/secret",
                "raw_model_output": "PRIVATE MODEL METADATA",
            }
        ],
        "validation_json": {"private_model_response": "SECRET"},
    }


def test_snapshot_binds_exact_values_and_private_evidence_without_exposing_them():
    row = sample()
    refs, complete = public_evidence(row["evidence_json"])
    assert complete and refs[0].source_engine == "qwen3_8_27b"
    snapshot, original = source_snapshot(row, None, None, refs)
    assert snapshot["candidate"]["net_amount"] == "99999999999999.9999"
    assert snapshot["candidate"]["plan_paid_amount"] == "0.0000"
    assert snapshot["candidate"]["allowed_amount"] == "-3.0001"
    assert "/private/" not in str(snapshot) and "SECRET" not in str(snapshot)
    changed = deepcopy(row)
    changed["evidence_json"][0]["uri"] = "/private/archive/changed"
    assert source_snapshot(changed, None, None, refs)[1] != original
    changed = deepcopy(row)
    changed["description"] = "Different service"
    assert source_snapshot(changed, None, None, refs)[1] != original
    row["status"] = "rejected"
    row["decision_version"] = uuid4()
    assert source_snapshot(row, None, None, refs)[1] == original


def test_incomplete_evidence_cannot_become_complete_by_dropping_refs():
    valid = sample()["evidence_json"][0]
    refs, complete = public_evidence([valid, {"pageNumber": 2, "sourceEngine": "qwen3_8_27b"}])
    assert len(refs) == 1 and not complete


def test_expanded_basis_has_explicit_distinct_identity_and_all_money_components():
    row = sample()
    baseline = selected_facts_digest([], [row])
    assert baseline != accepted_facts_digest([])
    for column in (
        "net_amount",
        "allowed_amount",
        "plan_paid_amount",
        "quantity",
        "decision_revision",
    ):
        changed = dict(row)
        changed[column] = uuid4() if column == "decision_revision" else Decimal("1.0000")
        assert selected_facts_digest([], [changed]) != baseline
