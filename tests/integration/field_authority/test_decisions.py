from uuid import uuid4

import pytest

from lib.db.connection import db_connection
from lib.fact_authority.preconditions import AuthorityRevisionConflict
from lib.review.correction_values import CorrectionValueError

from .support import (
    candidate,
    confirm,
    correct,
    envelope,
    preconditions,
    promote,
    reject,
    seed_chunk,
    snapshot,
)


def test_absent_canonical_rejection_is_durable_and_exact_revision_allows_replacement(
    promotion_document,
):
    document_id, access = promotion_document
    item = candidate(document_id, "Unaccepted candidate")
    seed_chunk(document_id)
    first = envelope(document_id, access)
    assert first.items == first.decisions == []
    assert first.projection.state == "unestablished"
    result = reject(document_id, access, item["field_path"])
    assert result.canonical is None and result.decision.canonical_field_id is None
    assert result.decision.disposition == "rejected"
    current = envelope(document_id, access)
    assert current.items == [] and current.decisions == [result.decision]
    assert current.projection.state == "current"
    assert current.projection.accepted_fact_revision == current.projection.projection_revision == 1
    assert promote(document_id, candidate(document_id, "Unwanted rerun")) == 0
    before = snapshot(document_id)
    for action in (
        lambda: confirm(document_id, access, item),
        lambda: correct(document_id, access, item["field_path"]),
        lambda: reject(
            document_id, access, item["field_path"], **preconditions(first, item["field_path"])
        ),
    ):
        with pytest.raises(AuthorityRevisionConflict):
            action()
        assert snapshot(document_id) == before
    replacement = correct(
        document_id, access, item["field_path"], **preconditions(current, item["field_path"])
    )
    assert replacement.decision.revision != result.decision.revision
    assert replacement.decision.disposition == "corrected"
    assert replacement.canonical.value == "Replacement from evidence"
    assert replacement.projection.accepted_fact_revision == 2
    assert replacement.projection.projection_revision == 2


def test_repeated_absent_rejection_requires_decision_revision_independent_of_canonical(
    promotion_document,
):
    document_id, access = promotion_document
    path = "invoice.purchase_order"
    reject(document_id, access, path)
    first = envelope(document_id, access)
    second = reject(document_id, access, path, **preconditions(first, path))
    assert second.canonical is None
    assert second.decision.revision != first.decisions[0].revision
    assert second.projection.accepted_fact_revision == first.projection.accepted_fact_revision
    assert second.projection.projection_revision == first.projection.projection_revision + 1
    before = snapshot(document_id)
    with pytest.raises(AuthorityRevisionConflict):
        correct(document_id, access, path, **preconditions(first, path))
    assert snapshot(document_id) == before


def test_active_legacy_path_guard_requires_acknowledgement_but_only_exact_field_can_override(
    promotion_document,
):
    document_id, access = promotion_document
    first = candidate(document_id, "Accepted old ordinal one")
    second = candidate(document_id, "Accepted old ordinal two")
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE field_candidates SET ordinal=2 WHERE id=%s RETURNING *", (second["id"],)
        )
        second = cur.fetchone()
    assert promote(document_id, first) == promote(document_id, second) == 1
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO canonical_field_path_guards(document_id,field_path) VALUES (%s,%s)",
            (document_id, first["field_path"]),
        )
        cur.execute(
            "SELECT count(*) AS count FROM selected_canonical_fields WHERE document_id=%s",
            (document_id,),
        )
        assert cur.fetchone()["count"] == 0
    before = snapshot(document_id)
    with pytest.raises(AuthorityRevisionConflict):
        confirm(document_id, access, first)
    assert snapshot(document_id) == before
    current = envelope(document_id, access)
    result = confirm(document_id, access, second, **preconditions(current, second["field_path"], 2))
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT ordinal FROM selected_canonical_fields WHERE document_id=%s", (document_id,)
        )
        assert [row["ordinal"] for row in cur.fetchall()] == [2]
    assert envelope(document_id, access).path_guards[0].status == "active"
    assert result.decision.ordinal == 2
    assert promote(document_id, first) == 0


@pytest.mark.parametrize("mismatch", ["path", "ordinal", "document"])
def test_explicit_candidate_identity_is_checked_before_confirmation_or_rejection(
    promotion_document, mismatch
):
    document_id, access = promotion_document
    item = candidate(document_id, "Exact field only")
    before = snapshot(document_id)
    with pytest.raises(CorrectionValueError):
        confirm(
            document_id,
            access,
            item,
            expected_field_path="invoice.wrong" if mismatch == "path" else item["field_path"],
            expected_ordinal=2 if mismatch != "path" else 1,
        )
    with pytest.raises(CorrectionValueError):
        reject(
            document_id,
            access,
            "invoice.wrong" if mismatch == "path" else item["field_path"],
            ordinal=2 if mismatch == "ordinal" else 1,
            selected_candidate_id=uuid4() if mismatch == "document" else item["id"],
        )
    assert snapshot(document_id) == before


def test_selected_view_never_exposes_rejection_even_if_legacy_row_status_is_accepted(
    promotion_document,
):
    document_id, access = promotion_document
    item = candidate(document_id, "Rejected secret field text")
    confirm(document_id, access, item)
    current = envelope(document_id, access)
    reject(document_id, access, item["field_path"], **preconditions(current, item["field_path"]))
    seed_chunk(document_id)
    with db_connection() as conn, conn.cursor() as cur:
        # Represents an old writer that only changes legacy status, not authority.
        cur.execute(
            "UPDATE canonical_fields SET review_status='auto_accepted' WHERE document_id=%s",
            (document_id,),
        )
        cur.execute("SELECT refresh_document_chunk_projection(%s)", (document_id,))
        cur.execute("SELECT bm25_text FROM document_chunks WHERE document_id=%s", (document_id,))
        assert item["text_value"] not in cur.fetchone()["bm25_text"]
        cur.execute(
            "SELECT count(*) AS count FROM selected_canonical_fields WHERE document_id=%s",
            (document_id,),
        )
        assert cur.fetchone()["count"] == 0
    assert promote(document_id, candidate(document_id, "Later model guess")) == 0
