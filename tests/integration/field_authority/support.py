"""Real-database fixtures and full transaction snapshots for field authority tests."""

from lib.db.connection import db_connection
from lib.fact_authority.models import RevisionExpectation
from lib.review import canonical_field_repository as fields
from lib.review.canonical_read_repository import get_canonical_field_response
from lib.review.correction_revision import CorrectionExpectation

from ..test_human_confirmed_promotion import candidate, promote

__all__ = ["candidate", "promote"]


def envelope(document_id, access):
    return get_canonical_field_response(document_id=document_id, access=access)


def preconditions(response, path, ordinal=1):
    canonical = next(
        (row for row in response.items if (row.field_path, row.ordinal) == (path, ordinal)), None
    )
    decision = next(
        (row for row in response.decisions if (row.field_path, row.ordinal) == (path, ordinal)),
        None,
    )
    guard = next(
        (row for row in response.path_guards if row.field_path == path and row.status == "active"),
        None,
    )
    return {
        "expectation": CorrectionExpectation(
            True, canonical.updated_at.isoformat() if canonical else None
        ),
        "decision_expectation": RevisionExpectation(
            supplied=True, revision=decision.revision if decision else None
        ),
        "path_guard_expectation": RevisionExpectation(
            supplied=True, revision=guard.revision if guard else None
        ),
    }


def confirm(document_id, access, item, **kwargs):
    return fields.confirm_candidate_result(
        document_id=document_id,
        access=access,
        actor_user_id=access.user_id,
        candidate_id=item["id"],
        reason="Original evidence checked",
        **kwargs,
    )


def reject(document_id, access, path, **kwargs):
    return fields.reject_field_result(
        document_id=document_id,
        access=access,
        actor_user_id=access.user_id,
        field_path=path,
        reason="Not an accepted fact",
        **kwargs,
    )


def correct(document_id, access, path, value="Replacement from evidence", **kwargs):
    return fields.correct_field_result(
        document_id=document_id,
        access=access,
        actor_user_id=access.user_id,
        field_path=path,
        value_type="string",
        value=value,
        evidence=[{"pageNumber": 1, "sourceEngine": "human", "sourceText": value}],
        **kwargs,
    )


def snapshot(document_id):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT jsonb_build_object(
          'document',(SELECT to_jsonb(d) FROM documents d WHERE id=%(id)s),
          'canonical',(SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM canonical_fields c
            WHERE document_id=%(id)s),
          'candidates',(SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM field_candidates c
            WHERE document_id=%(id)s),
          'decisions',(SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM canonical_field_decisions c
            WHERE document_id=%(id)s),
          'guards',(SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM canonical_field_path_guards c
            WHERE document_id=%(id)s),
          'history',(SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM canonical_fact_history c
            WHERE document_id=%(id)s),
          'events',(SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM review_events c
            WHERE document_id=%(id)s),
          'tasks',(SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM review_tasks c
            WHERE document_id=%(id)s),
          'projection',(SELECT to_jsonb(c) FROM document_fact_projection_state c
            WHERE document_id=%(id)s),
          'chunks',(SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM document_chunks c
            WHERE document_id=%(id)s),
          'amounts',(SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM document_amounts c
            WHERE document_id=%(id)s),
          'jobs',(SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM pipeline_jobs c
            WHERE document_id=%(id)s)
        ) AS snapshot""",
            {"id": document_id},
        )
        return cur.fetchone()["snapshot"]


def seed_chunk(document_id):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO document_chunks(document_id,chunk_index,text_content) "
            "VALUES (%s,0,'Original source text')",
            (document_id,),
        )
