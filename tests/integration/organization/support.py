"""Real filing requests and full before/after persistence evidence."""

from lib.contracts import DocumentOrganizationWrite, FolderWrite, TagWrite
from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext
from lib.organization.manual_filing import create_folder, create_tag, update_document_organization

from ..field_authority.support import candidate as field_candidate
from ..field_authority.support import confirm as confirm_field
from ..field_authority.support import snapshot as field_snapshot
from ..line_items.support import candidate, create_request, decide
from ..line_items.support import snapshot as line_snapshot


def file_document(doc, **changes):
    return update_document_organization(
        document_id=doc.document_id,
        payload=DocumentOrganizationWrite.model_validate(changes),
        principal=doc.principal,
    )


def collections(doc):
    folder = create_folder(FolderWrite(folderKind="manual", name="Claims"), doc.principal)
    tag = create_tag(TagWrite(name="evidence-tag"), doc.principal)
    return folder, tag


def established_facts(doc):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE documents SET document_date='2020-03-04' WHERE id=%s", (doc.document_id,)
        )
        cur.execute(
            "INSERT INTO document_metadata_decisions "
            "(document_id,property,value_json,origin,actor_user_id,decided_at) "
            "VALUES(%s,'document_date','\"2020-03-04\"','live_review',%s,clock_timestamp())",
            (doc.document_id, doc.credential.user_id),
        )
    field = field_candidate(doc.document_id, "Exact accepted field")
    access = DocumentAccessContext(doc.credential.household_id, doc.credential.user_id, "owner")
    confirm_field(doc.document_id, access, field)
    line = candidate(doc, "Exact accepted line")
    decide(doc, create_request(doc, line))


def impact(doc):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT
          (SELECT jsonb_agg(to_jsonb(c) ORDER BY folder_id) FROM document_folder_memberships c
            WHERE document_id=%(id)s) folders,
          (SELECT jsonb_agg(to_jsonb(c) ORDER BY tag_id) FROM document_tags c
            WHERE document_id=%(id)s) tags,
          (SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM audit_events c
            WHERE document_id=%(id)s) audits,
          (SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM filing_rule_runs c
            WHERE document_id=%(id)s) rules,
          (SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM document_metadata_decisions c
            WHERE document_id=%(id)s) metadata_decisions""",
            {"id": doc.document_id},
        )
        filing = cur.fetchone()
        cur.execute(
            "SELECT id,quantity::text,net_amount::text,gross_amount::text,allowed_amount::text,"
            "plan_paid_amount::text,currency_code FROM canonical_line_items "
            "WHERE document_id=%s ORDER BY id",
            (doc.document_id,),
        )
        exact_line_values = cur.fetchall()
    return {
        "fields": field_snapshot(doc.document_id),
        "lines": line_snapshot(doc),
        "filing": filing,
        "exact_line_values": exact_line_values,
    }


def assert_fact_basis_preserved(before, after):
    assert after["exact_line_values"] == before["exact_line_values"]
    for key in (
        "canonical",
        "candidates",
        "decisions",
        "guards",
        "history",
        "events",
        "tasks",
        "amounts",
    ):
        assert after["fields"][key] == before["fields"][key]
    for key in (
        "canonical",
        "candidates",
        "candidate_decisions",
        "decisions",
        "bindings",
        "history",
        "events",
        "tasks",
    ):
        assert after["lines"][key] == before["lines"][key]
    assert after["filing"]["metadata_decisions"] == before["filing"]["metadata_decisions"]
    previous, current = before["fields"]["projection"], after["fields"]["projection"]
    if previous is None or previous["state"] == "unestablished":
        assert current == previous
    else:
        for key in previous:
            if key not in {"indexed_metadata_sha256", "projection_revision", "recorded_at"}:
                assert current[key] == previous[key]
