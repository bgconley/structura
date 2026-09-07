"""Coherent canonical rows, durable decisions and projection state for one document."""

from uuid import UUID

from lib.contracts import CanonicalFieldResponse, FieldPathGuard
from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext
from lib.fact_authority.field_repository import decision_from_row, guard_from_row
from lib.fact_authority.models import ProjectionRevision
from lib.fact_authority.response_mapping import decision_response, projection_response
from lib.review.access import assert_readable
from lib.review.errors import ReviewRepositoryError
from lib.review.mappers import canonical_field_from_row


def get_canonical_field_response(
    *,
    document_id: UUID,
    access: DocumentAccessContext,
) -> CanonicalFieldResponse:
    with db_connection() as conn, conn.cursor() as cur:
        # Every source writer serializes on the document. Hold this read lock
        # through all component queries, then recheck ACL after any wait.
        cur.execute("SELECT id FROM documents WHERE id=%s FOR SHARE", (document_id,))
        if cur.fetchone() is None:
            raise ReviewRepositoryError("Document not found.")
        assert_readable(cur, document_id, access)
        cur.execute(
            "SELECT * FROM canonical_fields WHERE document_id=%s ORDER BY field_path,ordinal",
            (document_id,),
        )
        items = [canonical_field_from_row(row) for row in cur.fetchall()]
        cur.execute(
            "SELECT * FROM canonical_field_decisions WHERE document_id=%s "
            "ORDER BY field_path,ordinal",
            (document_id,),
        )
        decisions = [decision_response(decision_from_row(row)) for row in cur.fetchall()]
        by_identity = {(item.field_path, item.ordinal): item for item in decisions}
        for item in items:
            item.decision = by_identity.get((item.field_path, item.ordinal or 1))
        cur.execute(
            "SELECT * FROM canonical_field_path_guards WHERE document_id=%s ORDER BY field_path",
            (document_id,),
        )
        guards = [
            FieldPathGuard.model_validate(guard_from_row(row).model_dump())
            for row in cur.fetchall()
        ]
        cur.execute(
            "SELECT document_id,state,accepted_fact_revision,projection_revision,"
            "accepted_facts_sha256,indexed_metadata_sha256,accepted_fact_basis_schema_version "
            "FROM document_fact_projection_state "
            "WHERE document_id=%s",
            (document_id,),
        )
        row = cur.fetchone()
        projection = (
            ProjectionRevision(**row)
            if row
            else ProjectionRevision(
                document_id=document_id,
                state="unestablished",
                accepted_fact_revision=0,
                projection_revision=0,
                accepted_facts_sha256=None,
                indexed_metadata_sha256=None,
            )
        )
    return CanonicalFieldResponse(
        authorityVersion="human_authority.v1",
        items=items,
        decisions=decisions,
        pathGuards=guards,
        projection=projection_response(projection),
    )
