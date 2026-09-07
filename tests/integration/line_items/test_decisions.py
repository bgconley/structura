import pytest
from psycopg.types.json import Jsonb

from lib.db.connection import db_connection
from lib.review.line_items.errors import LineDecisionConflict, LineEvidenceError
from lib.review.line_items.history_read import line_history
from lib.review.line_items.read_repository import canonical_lines

from .support import candidate, create_request, decide, expected_source, snapshot, source, target


def test_publication_has_exact_complete_values_history_and_atomic_projection(line_document):
    doc = line_document
    item = candidate(doc)
    result = decide(doc, create_request(doc, item))
    value = result.canonical_item.model_dump(mode="json", by_alias=True)
    assert value["netAmount"] == "99999999999999.9999"
    assert value["allowedAmount"] == "0.0000" and value["planPaidAmount"] == "-3.0001"
    assert value["currency"] is None and value["selected"]
    assert result.projection.accepted_fact_basis_schema_version == "accepted_fields_and_lines.v1"
    state = snapshot(doc)
    assert len(state["history"]) == len(state["jobs"]) == len(state["bindings"]) == 1
    assert "Reviewed service" in state["chunks"][0]["bm25_text"]
    history = line_history(
        document_id=doc.document_id,
        credential=doc.credential,
        canonical_line_item_id=result.canonical_item.id,
    )
    assert history.items[0].after.canonical.net_amount == result.canonical_item.net_amount
    assert history.items[0].source.candidate.id == item


def test_rejecting_unselected_same_ordinal_proposal_preserves_selected_fact_and_other_tasks(
    line_document,
):
    doc = line_document
    first, second = candidate(doc, "First line"), candidate(doc, "Different proposal")
    selected = decide(doc, create_request(doc, first))
    with db_connection() as conn, conn.cursor() as cur:
        for item in (first, second):
            cur.execute(
                "INSERT INTO review_tasks(document_id,task_type,status,metadata_json) "
                "VALUES(%s,'field_review','open',%s)",
                (
                    doc.document_id,
                    Jsonb(
                        {
                            "lineItemCandidateId": str(item),
                            "lineItemType": "service_line",
                            "ordinal": 1,
                        }
                    ),
                ),
            )
    decide(doc, {"operation": "reject_candidate", "source": expected_source(source(doc, second))})
    envelope = canonical_lines(document_id=doc.document_id, credential=doc.credential)
    assert envelope.items[0].id == selected.canonical_item.id and envelope.items[0].selected
    states = {
        row["metadata_json"]["lineItemCandidateId"]: row["status"] for row in snapshot(doc)["tasks"]
    }
    assert states == {str(first): "open", str(second): "resolved"}
    with pytest.raises(LineDecisionConflict):
        decide(
            doc, {"operation": "reject_candidate", "source": expected_source(source(doc, first))}
        )


def test_lifetime_assignment_cannot_move_even_after_rejection(line_document):
    doc = line_document
    item = candidate(doc)
    selected = decide(doc, create_request(doc, item))
    canonical_id = selected.canonical_item.id
    old_target = target(doc, canonical_id)
    rejected = decide(doc, {"operation": "reject_selected", "target": old_target})
    assert not rejected.canonical_item.selected
    with pytest.raises(LineDecisionConflict):
        decide(doc, create_request(doc, item, ordinal=2))
    restored = decide(
        doc,
        {
            "operation": "replace",
            "source": expected_source(source(doc, item)),
            "target": target(doc, canonical_id),
        },
    )
    assert restored.canonical_item.id == canonical_id and restored.canonical_item.selected
    with pytest.raises(LineDecisionConflict):
        decide(doc, {"operation": "reject_selected", "target": old_target})


@pytest.mark.parametrize(
    "evidence",
    [
        [],
        [{"pageNumber": 1, "sourceEngine": "validator", "sourceText": ""}],
        [{"pageNumber": 1, "sourceEngine": "validator", "bbox": [1, 1, 0, 0]}],
        [{"pageNumber": 1, "sourceEngine": "validator", "textSpan": {"start": 25, "end": 5}}],
        [{"pageNumber": 2, "sourceEngine": "validator", "sourceText": "Missing page"}],
    ],
)
def test_incomplete_or_malformed_source_evidence_stays_readable_but_cannot_publish(
    line_document, evidence
):
    doc = line_document
    item = candidate(doc, evidence=evidence)
    assert source(doc, item)["publicationEligibility"]["reason"] == "evidence_incomplete"
    before = snapshot(doc)
    with pytest.raises(LineEvidenceError):
        decide(doc, create_request(doc, item))
    assert snapshot(doc) == before


def test_exact_last_source_survives_two_replacements_and_candidate_event_deletion(line_document):
    doc = line_document
    first, second = candidate(doc, "First source"), candidate(doc, "Last selected source")
    created = decide(doc, create_request(doc, first))
    canonical_id = created.canonical_item.id
    replaced = decide(
        doc,
        {
            "operation": "replace",
            "source": expected_source(source(doc, second)),
            "target": target(doc, canonical_id),
        },
    )
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM line_item_candidates WHERE id=%s", (second,))
        cur.execute("DELETE FROM review_events WHERE id=%s", (replaced.event_id,))
    decide(doc, {"operation": "reject_selected", "target": target(doc, canonical_id)})
    history = line_history(
        document_id=doc.document_id, credential=doc.credential, source_candidate_id=second
    )
    assert history.items[0].operation == "reject_selected"
    assert history.items[0].before.source.candidate.id == second
    assert history.items[0].after.source.candidate.id == second
    assert history.items[0].before.source_coverage == "recorded"


def test_contradictory_candidate_task_path_is_not_closed_by_an_exact_line_decision(line_document):
    doc = line_document
    item = candidate(doc)
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO review_tasks(document_id,task_type,status,metadata_json) "
            "VALUES(%s,'field_review','open',%s) RETURNING id",
            (
                doc.document_id,
                Jsonb(
                    {"lineItemCandidateId": str(item), "fieldPath": "line_items.service_line.999"}
                ),
            ),
        )
        task_id = cur.fetchone()["id"]
    decide(doc, create_request(doc, item))
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT status FROM review_tasks WHERE id=%s", (task_id,))
        assert cur.fetchone()["status"] == "open"
