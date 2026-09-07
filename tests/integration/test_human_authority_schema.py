"""099 foundation checks; review-writer/rerun races belong to its activation slice."""

from pathlib import Path
from typing import LiteralString, cast
from uuid import uuid4

import pytest
from psycopg.errors import CheckViolation, ForeignKeyViolation, RaiseException
from psycopg.sql import SQL
from psycopg.types.json import Jsonb

from lib.db.connection import db_connection

from .test_human_confirmed_promotion import promotion_document as promotion_document


def reapply_099(cur):
    # Reconstruct the actual pre-099 shape inside this test transaction only.
    cur.execute(
        "DROP TABLE canonical_field_decisions,canonical_field_path_guards,"
        "document_metadata_decisions,document_fact_projection_state"
    )
    cur.execute(
        "DROP FUNCTION preserve_human_authority_record(),"
        "preserve_fact_projection_revision(),valid_manual_metadata_value(text,jsonb)"
    )
    cur.execute("ALTER TABLE canonical_fields DROP CONSTRAINT canonical_fields_authority_identity")
    cur.execute("ALTER TABLE review_events DROP CONSTRAINT review_events_authority_identity")
    cur.execute("ALTER TABLE audit_events DROP CONSTRAINT audit_events_authority_identity")
    migration = (
        Path(__file__).resolve().parents[2] / "database/099_completion_human_fact_authority.sql"
    ).read_text()
    cur.execute(SQL(cast(LiteralString, migration)), prepare=False)


def insert_field(cur, document_id, path, status, source="candidate"):
    cur.execute(
        """INSERT INTO canonical_fields
        (document_id,field_path,value_type,text_value,source_kind,review_status)
        VALUES (%s,%s,'string','Retained source value',%s,%s) RETURNING id""",
        (document_id, path, source, status),
    )
    return cur.fetchone()["id"]


def review_event(cur, document_id, path, action, value=None):
    cur.execute(
        """INSERT INTO review_events (document_id,field_path,action,new_value_json)
        VALUES (%s,%s,%s,%s) RETURNING id""",
        (document_id, path, action, Jsonb(value)),
    )
    return cur.fetchone()["id"]


@pytest.mark.parametrize(
    "families,has_binding",
    [
        (("receipt", "invoice"), False),
        (("receipt",), False),
        (("invoice", "invoice"), True),
    ],
)
def test_upgrade_preserves_rejected_and_unknown_authority_without_restoring_metadata(
    promotion_document,
    families,
    has_binding,
):
    document_id, _ = promotion_document
    with db_connection() as conn, conn.cursor() as cur:
        # A physically deleted reviewer is independent from retained human status.
        cur.execute(
            "INSERT INTO users(email,display_name) VALUES (%s,'Former reviewer') RETURNING id",
            (f"authority-upgrade-{uuid4()}@example.com",),
        )
        actor = cur.fetchone()["id"]
        confirmed = insert_field(cur, document_id, "invoice.confirmed", "user_confirmed")
        cur.execute(
            "UPDATE canonical_fields SET accepted_by_user_id=%s WHERE id=%s", (actor, confirmed)
        )
        cur.execute("DELETE FROM users WHERE id=%s", (actor,))
        insert_field(cur, document_id, "invoice.human_rejected", "rejected", "human")
        insert_field(cur, document_id, "invoice.unknown", "needs_review", "human")
        # Old machine-origin rejection lacks all human markers. Its event must
        # retain path-wide authority without inventing an ordinal or accepted row.
        insert_field(cur, document_id, "invoice.machine_rejected", "rejected")
        review_event(cur, document_id, "invoice.machine_rejected", "reject_field")
        review_event(cur, document_id, "invoice.never_promoted", "reject_field")
        for family in families:
            review_event(
                cur,
                document_id,
                "classification.document_family",
                "reclassify_document",
                {"family": family, "subtype": None},
            )
        cur.execute(
            "UPDATE documents SET document_family='invoice',document_date=NULL WHERE id=%s",
            (document_id,),
        )
        cur.execute(
            """INSERT INTO audit_events(entity_type,document_id,event_name,payload_json)
            VALUES ('document',%s,'document.organization_updated',%s)""",
            (
                document_id,
                Jsonb({"changed_fields": ["documentDate"], "after": {"documentDate": None}}),
            ),
        )
        cur.execute("SELECT to_jsonb(d) AS value FROM documents d WHERE id=%s", (document_id,))
        before_document = cur.fetchone()["value"]
        cur.execute(
            "SELECT count(*) AS n FROM canonical_fields WHERE document_id=%s", (document_id,)
        )
        before_count = cur.fetchone()["n"]
        reapply_099(cur)
        cur.execute(
            "SELECT field_path,disposition,actor_user_id FROM canonical_field_decisions "
            "WHERE document_id=%s",
            (document_id,),
        )
        decisions = {r["field_path"]: r for r in cur.fetchall()}
        assert {path: r["disposition"] for path, r in decisions.items()} == {
            "invoice.confirmed": "confirmed",
            "invoice.human_rejected": "rejected",
            "invoice.unknown": "protected_legacy",
        }
        assert decisions["invoice.confirmed"]["actor_user_id"] is None
        cur.execute(
            "SELECT field_path,status FROM canonical_field_path_guards WHERE document_id=%s",
            (document_id,),
        )
        assert {r["field_path"]: r["status"] for r in cur.fetchall()} == {
            "invoice.machine_rejected": "active",
            "invoice.never_promoted": "active",
        }
        cur.execute(
            "SELECT property,value_json FROM document_metadata_decisions WHERE document_id=%s",
            (document_id,),
        )
        metadata = {row["property"]: row["value_json"] for row in cur.fetchall()}
        assert metadata == (
            {"document_date": None, "classification": {"family": "invoice", "subtype": None}}
            if has_binding
            else {"document_date": None}
        )
        cur.execute(
            "SELECT state,accepted_fact_revision,accepted_facts_sha256 "
            "FROM document_fact_projection_state WHERE document_id=%s",
            (document_id,),
        )
        assert cur.fetchone() == {
            "state": "unestablished",
            "accepted_fact_revision": 0,
            "accepted_facts_sha256": None,
        }
        cur.execute("SELECT to_jsonb(d) AS value FROM documents d WHERE id=%s", (document_id,))
        assert cur.fetchone()["value"] == before_document
        cur.execute(
            "SELECT count(*) AS n FROM canonical_fields WHERE document_id=%s", (document_id,)
        )
        assert cur.fetchone()["n"] == before_count
        conn.rollback()


@pytest.mark.parametrize(
    "property_name,value,valid",
    [
        ("classification", {"family": "invoice", "subtype": None}, True),
        ("classification", {"family": None, "subtype": None}, False),
        ("classification", {"family": "invoice"}, False),
        ("classification", {"family": "invented", "subtype": None}, False),
        ("classification", {"family": "invoice", "subtype": None, "extra": True}, False),
        ("classification", None, False),
        ("classification", 1, False),
        ("classification", [], False),
        ("document_date", None, True),
        ("document_date", "2026-09-07", True),
        ("document_date", "2026-02-30", False),
        ("document_date", "2026-00-01", False),
        ("document_date", True, False),
        ("document_date", 0, False),
    ],
)
def test_metadata_value_validation_never_passes_on_sql_unknown(
    promotion_document, property_name, value, valid
):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT valid_manual_metadata_value(%s,%s) AS valid", (property_name, Jsonb(value))
        )
        assert cur.fetchone()["valid"] is valid
        cur.execute("SELECT valid_manual_metadata_value(%s,NULL) AS valid", (property_name,))
        assert cur.fetchone()["valid"] is False


def test_decision_revisions_reference_cleanup_and_populated_document_cascade(promotion_document):
    document_id, _ = promotion_document
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users(email,display_name) VALUES (%s,'Deciding user') RETURNING id",
            (f"authority-retention-{uuid4()}@example.com",),
        )
        actor = cur.fetchone()["id"]
        canonical = insert_field(cur, document_id, "invoice.total", "user_confirmed")
        event = review_event(cur, document_id, "invoice.total", "confirm_field")
        cur.execute(
            """INSERT INTO canonical_field_decisions
            (document_id,field_path,ordinal,disposition,origin,canonical_field_id,review_event_id,
             actor_user_id,decided_at)
            VALUES (%s,'invoice.total',1,'confirmed','live_review',%s,%s,%s,now())
            RETURNING id,revision,recorded_at""",
            (document_id, canonical, event, actor),
        )
        decision = cur.fetchone()
        cur.execute("SAVEPOINT invalid_field_reference")
        with pytest.raises(ForeignKeyViolation):
            cur.execute(
                """INSERT INTO canonical_field_decisions(document_id,field_path,ordinal,disposition,
                origin,canonical_field_id,decided_at)
                VALUES (%s,'invoice.different_path',1,'confirmed','live_review',%s,now())""",
                (document_id, canonical),
            )
            cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cur.execute("ROLLBACK TO SAVEPOINT invalid_field_reference")
        updates: tuple[LiteralString, ...] = (
            "UPDATE canonical_field_decisions SET disposition='rejected' WHERE id=%s",
            "UPDATE canonical_field_decisions SET revision=gen_random_uuid() WHERE id=%s",
            "DELETE FROM canonical_field_decisions WHERE id=%s",
        )
        for update in updates:
            cur.execute("SAVEPOINT forbidden")
            with pytest.raises(RaiseException):
                cur.execute(SQL(update), (decision["id"],))
            cur.execute("ROLLBACK TO SAVEPOINT forbidden")
        cur.execute(
            """UPDATE canonical_field_decisions SET disposition='rejected',
            revision=gen_random_uuid(),
            recorded_at=clock_timestamp() WHERE id=%s RETURNING revision""",
            (decision["id"],),
        )
        revision = cur.fetchone()["revision"]
        assert revision != decision["revision"]
        cur.execute("DELETE FROM users WHERE id=%s", (actor,))
        cur.execute("DELETE FROM canonical_fields WHERE id=%s", (canonical,))
        cur.execute(
            "SELECT disposition,revision,actor_user_id,canonical_field_id "
            "FROM canonical_field_decisions "
            "WHERE id=%s",
            (decision["id"],),
        )
        assert cur.fetchone() == {
            "disposition": "rejected",
            "revision": revision,
            "actor_user_id": None,
            "canonical_field_id": None,
        }
        # Keep another exact canonical FK populated during the final document cascade.
        second = insert_field(cur, document_id, "invoice.retained", "user_corrected")
        second_event = review_event(cur, document_id, "invoice.retained", "correct_field")
        cur.execute(
            """INSERT INTO canonical_field_decisions(document_id,field_path,ordinal,disposition,
            origin,canonical_field_id,review_event_id,decided_at)
            VALUES (%s,'invoice.retained',1,'corrected','live_review',%s,%s,now())""",
            (document_id, second, second_event),
        )
        cur.execute("SAVEPOINT missing_decision_time")
        with pytest.raises(CheckViolation):
            cur.execute(
                """INSERT INTO canonical_field_decisions(document_id,field_path,ordinal,
                disposition,origin)
                VALUES (%s,'invoice.no_timestamp',1,'rejected','live_review')""",
                (document_id,),
            )
        cur.execute("ROLLBACK TO SAVEPOINT missing_decision_time")
        cur.execute(
            "INSERT INTO canonical_field_path_guards(document_id,field_path,review_event_id) "
            "VALUES (%s,'invoice.total',%s)",
            (document_id, event),
        )
        classification_event = review_event(
            cur,
            document_id,
            "classification.document_family",
            "reclassify_document",
            {"family": "invoice", "subtype": None},
        )
        cur.execute(
            "INSERT INTO document_metadata_decisions(document_id,property,value_json,origin,"
            "review_event_id,decided_at) VALUES (%s,'classification',%s,'live_review',%s,now())",
            (document_id, Jsonb({"family": "invoice", "subtype": None}), classification_event),
        )
        cur.execute(
            "INSERT INTO audit_events(entity_type,document_id,event_name) "
            "VALUES ('document',%s,'document.organization_updated') RETURNING id",
            (document_id,),
        )
        audit_id = cur.fetchone()["id"]
        cur.execute(
            "INSERT INTO document_metadata_decisions(document_id,property,value_json,origin,"
            "audit_event_id,decided_at) VALUES (%s,'document_date','null','live_review',%s,now())",
            (document_id, audit_id),
        )
        cur.execute(
            "INSERT INTO document_fact_projection_state(document_id,legacy_metadata_json) "
            "VALUES (%s,'{}') ON CONFLICT DO NOTHING",
            (document_id,),
        )
        cur.execute("DELETE FROM documents WHERE id=%s", (document_id,))
        # Force deferred cross-table FKs before rollback, so this cannot pass on
        # an inconsistent state that would fail only at an actual commit.
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cur.execute(
            "SELECT (SELECT count(*) FROM canonical_field_decisions WHERE document_id=%(id)s) + "
            "(SELECT count(*) FROM canonical_field_path_guards WHERE document_id=%(id)s) + "
            "(SELECT count(*) FROM document_metadata_decisions WHERE document_id=%(id)s) + "
            "(SELECT count(*) FROM document_fact_projection_state WHERE document_id=%(id)s) AS n",
            {"id": document_id},
        )
        assert cur.fetchone()["n"] == 0
        conn.rollback()


def test_projection_hash_change_requires_fact_revision_and_monotonic_projection(promotion_document):
    document_id, _ = promotion_document
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO document_fact_projection_state(document_id,legacy_metadata_json) "
            "VALUES (%s,'{}') ON CONFLICT DO NOTHING",
            (document_id,),
        )
        cur.execute("SAVEPOINT empty_current")
        with pytest.raises(CheckViolation):
            cur.execute(
                "UPDATE document_fact_projection_state SET state='current',projection_revision=1,"
                "recorded_at=clock_timestamp() WHERE document_id=%s",
                (document_id,),
            )
        cur.execute("ROLLBACK TO SAVEPOINT empty_current")
        cur.execute(
            "UPDATE document_fact_projection_state SET state='current',accepted_fact_revision=1,"
            "projection_revision=1,accepted_facts_sha256=%s,indexed_metadata_sha256=%s,rollup_json='{}',"
            "recorded_at=clock_timestamp() WHERE document_id=%s",
            ("a" * 64, "b" * 64, document_id),
        )
        cur.execute("SAVEPOINT stale_fact_revision")
        with pytest.raises(RaiseException, match="monotonic"):
            cur.execute(
                "UPDATE document_fact_projection_state SET accepted_facts_sha256=%s,"
                "projection_revision=2,recorded_at=clock_timestamp() WHERE document_id=%s",
                ("c" * 64, document_id),
            )
        cur.execute("ROLLBACK TO SAVEPOINT stale_fact_revision")
        cur.execute(
            "UPDATE document_fact_projection_state SET indexed_metadata_sha256=%s,"
            "projection_revision=2,recorded_at=clock_timestamp() WHERE document_id=%s",
            ("d" * 64, document_id),
        )
        cur.execute(
            "SELECT accepted_fact_revision,projection_revision FROM document_fact_projection_state "
            "WHERE document_id=%s",
            (document_id,),
        )
        assert cur.fetchone() == {"accepted_fact_revision": 1, "projection_revision": 2}
        conn.rollback()
