from pathlib import Path
from typing import LiteralString, cast
from uuid import uuid4

import pytest
from psycopg.errors import CheckViolation, ForeignKeyViolation, RaiseException
from psycopg.sql import SQL

from lib.db.connection import db_connection

from .support import candidate, create_request, decide


def pre_103(cur):
    cur.execute("DROP VIEW selected_canonical_line_items")
    cur.execute(
        "DROP TABLE canonical_line_item_decisions,line_item_candidate_decisions,"
        "canonical_line_item_source_bindings,line_item_decision_events CASCADE"
    )
    cur.execute("DROP TRIGGER line_candidate_version ON line_item_candidates")
    cur.execute(
        "ALTER TABLE canonical_line_items DROP CONSTRAINT canonical_line_candidate_document"
    )
    cur.execute("DROP FUNCTION version_line_candidate(),preserve_line_authority()")
    cur.execute("DROP TRIGGER line_fact_basis_revision ON document_fact_projection_state")
    cur.execute("DROP FUNCTION preserve_line_fact_basis()")
    cur.execute(
        "ALTER TABLE canonical_line_items DROP COLUMN allowed_amount,DROP COLUMN plan_paid_amount,"
        "DROP CONSTRAINT canonical_line_authority_identity"
    )
    cur.execute(
        "ALTER TABLE line_item_candidates DROP COLUMN decision_version,"
        "DROP CONSTRAINT line_candidate_authority_identity,DROP CONSTRAINT "
        "line_candidate_extraction_document"
    )
    cur.execute(
        "ALTER TABLE document_extractions DROP CONSTRAINT extraction_line_authority_identity"
    )
    cur.execute(
        "ALTER TABLE document_fact_projection_state DROP COLUMN accepted_fact_basis_schema_version"
    )


def apply_103(cur):
    migration = (
        Path(__file__).resolve().parents[3] / "database/103_completion_line_item_authority.sql"
    ).read_text()
    cur.execute(SQL(cast(LiteralString, migration)), prepare=False)


def test_upgrade_preserves_legacy_duplicate_assignment_and_human_data_without_publishing_guesses(
    line_document,
):
    doc = line_document
    item = candidate(doc)
    with db_connection() as conn, conn.cursor() as cur:
        pre_103(cur)
        cur.execute(
            "INSERT INTO users(email,display_name) VALUES(%s,'Deleted accepting "
            "actor') RETURNING id",
            (f"deleted-line-{uuid4()}@example.com",),
        )
        actor = cur.fetchone()["id"]
        for ordinal, status, kind in [
            (1, "user_corrected", "candidate"),
            (2, "auto_accepted", "system"),
            (3, "needs_review", "human"),
            (4, "rejected", "human"),
        ]:
            cur.execute(
                """INSERT INTO canonical_line_items(document_id,line_item_type,ordinal,
            selected_candidate_id,description,net_amount,source_kind,review_status,accepted_by_user_id)
            VALUES(%s,'service_line',%s,%s,'Retained actual line',12.3400,%s,%s,%s)""",
                (
                    doc.document_id,
                    ordinal,
                    item if ordinal in (1, 2) else None,
                    kind,
                    status,
                    actor if ordinal == 1 else None,
                ),
            )
        cur.execute("DELETE FROM users WHERE id=%s", (actor,))
        cur.execute(
            "SELECT ordinal,description,net_amount FROM canonical_line_items WHERE "
            "document_id=%s ORDER BY ordinal",
            (doc.document_id,),
        )
        before = cur.fetchall()
        apply_103(cur)
        cur.execute(
            "SELECT ordinal,description,net_amount FROM canonical_line_items WHERE "
            "document_id=%s ORDER BY ordinal",
            (doc.document_id,),
        )
        assert cur.fetchall() == before
        cur.execute(
            "SELECT ordinal,disposition,actor_user_id FROM "
            "canonical_line_item_decisions WHERE document_id=%s ORDER BY ordinal",
            (doc.document_id,),
        )
        assert cur.fetchall() == [
            {"ordinal": 1, "disposition": "corrected", "actor_user_id": None},
            {"ordinal": 3, "disposition": "protected_legacy", "actor_user_id": None},
            {"ordinal": 4, "disposition": "rejected", "actor_user_id": None},
        ]
        cur.execute(
            "SELECT binding_state,canonical_line_item_id FROM "
            "canonical_line_item_source_bindings WHERE document_id=%s",
            (doc.document_id,),
        )
        assert cur.fetchone() == {
            "binding_state": "legacy_conflict",
            "canonical_line_item_id": None,
        }
        cur.execute(
            "SELECT ordinal FROM selected_canonical_line_items WHERE document_id=%s "
            "ORDER BY ordinal",
            (doc.document_id,),
        )
        assert [row["ordinal"] for row in cur.fetchall()] == [1, 2]
        cur.execute(
            "SELECT convalidated FROM pg_constraint WHERE "
            "conname='canonical_line_selected_source_binding'"
        )
        assert cur.fetchone()["convalidated"] is False
        conn.rollback()


@pytest.mark.parametrize(
    "mutation",
    [
        "decision_delete",
        "binding_delete",
        "history_delete",
        "canonical_delete",
        "candidate_content",
        "candidate_identity",
        "decision_revision",
        "binding_null_ordinal",
    ],
)
def test_retained_line_authority_and_source_identity_reject_individual_mutation(
    line_document, mutation
):
    doc = line_document
    item = candidate(doc)
    result = decide(doc, create_request(doc, item))
    with db_connection() as conn, conn.cursor() as cur:
        with pytest.raises((RaiseException, ForeignKeyViolation, CheckViolation)):
            if mutation == "decision_delete":
                cur.execute(
                    "DELETE FROM canonical_line_item_decisions WHERE document_id=%s",
                    (doc.document_id,),
                )
            elif mutation == "binding_delete":
                cur.execute(
                    "DELETE FROM canonical_line_item_source_bindings WHERE document_id=%s",
                    (doc.document_id,),
                )
            elif mutation == "history_delete":
                cur.execute(
                    "DELETE FROM line_item_decision_events WHERE document_id=%s", (doc.document_id,)
                )
            elif mutation == "canonical_delete":
                cur.execute(
                    "DELETE FROM canonical_line_items WHERE id=%s", (result.canonical_item.id,)
                )
            elif mutation == "candidate_content":
                cur.execute(
                    "UPDATE line_item_candidates SET description='Changed source' WHERE id=%s",
                    (item,),
                )
            elif mutation == "candidate_identity":
                cur.execute(
                    "UPDATE line_item_candidates SET extraction_id=NULL WHERE id=%s", (item,)
                )
            elif mutation == "decision_revision":
                cur.execute(
                    "UPDATE canonical_line_item_decisions SET disposition='rejected' "
                    "WHERE document_id=%s",
                    (doc.document_id,),
                )
            else:
                cur.execute(
                    """INSERT INTO canonical_line_item_source_bindings
                (document_id,source_candidate_id,binding_state,canonical_line_item_id,line_item_type,ordinal,
                 source_snapshot_json,source_snapshot_sha256)
                VALUES(%s,%s,'assigned',%s,'service_line',NULL,'{}',%s)""",
                    (doc.document_id, uuid4(), result.canonical_item.id, "b" * 64),
                )
            conn.commit()
        conn.rollback()


def test_all_populated_references_cascade_with_physical_document_delete(line_document):
    doc = line_document
    result = decide(doc, create_request(doc, candidate(doc)))
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE id=%s", (doc.document_id,))
        conn.commit()
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM line_item_decision_events WHERE id=%s", (result.event_id,))
        assert cur.fetchone() is None
        cur.execute("SELECT id FROM canonical_line_items WHERE id=%s", (result.canonical_item.id,))
        assert cur.fetchone() is None


def test_legacy_foreign_extraction_cannot_leak_provenance_on_candidate_rejection(line_document):
    doc = line_document
    item = candidate(doc)
    with db_connection() as conn, conn.cursor() as cur:
        # Exercise the actual NOT VALID upgrade case, then rollback schema+data.
        pre_103(cur)
        cur.execute(
            "INSERT INTO documents(title,ingestion_source,household_id,owner_user_id) "
            "VALUES('Foreign scope','web_upload',%s,%s) RETURNING id",
            (doc.credential.household_id, doc.credential.user_id),
        )
        foreign = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO "
            "document_extractions(document_id,schema_name,schema_version,model_name,"
            "source_engine,status) "
            "VALUES(%s,'PRIVATE_FOREIGN_SCHEMA','v1','PRIVATE_FOREIGN_MODEL',"
            "'validator','completed') "
            "RETURNING id",
            (foreign,),
        )
        foreign_extraction = cur.fetchone()["id"]
        cur.execute(
            "UPDATE line_item_candidates SET extraction_id=%s WHERE id=%s",
            (foreign_extraction, item),
        )
        apply_103(cur)
        from lib.review.line_items.source_repository import read_source

        observed = read_source(cur, doc.document_id, item)
        assert observed.eligibility.reason == "source_binding_invalid"
        assert observed.snapshot["extraction"] is None
        assert "PRIVATE_FOREIGN" not in str(observed.snapshot)
        conn.rollback()


def test_expanded_accepted_basis_cannot_be_downgraded(line_document):
    doc = line_document
    decide(doc, create_request(doc, candidate(doc)))
    with db_connection() as conn, conn.cursor() as cur:
        with pytest.raises(RaiseException):
            cur.execute(
                """UPDATE document_fact_projection_state
              SET accepted_fact_basis_schema_version='accepted_fields.v1',accepted_facts_sha256=%s,
                  accepted_fact_revision=accepted_fact_revision+1,projection_revision=projection_revision+1,
                  recorded_at=clock_timestamp()+interval '1 second'
              WHERE document_id=%s""",
                ("b" * 64, doc.document_id),
            )
        conn.rollback()
