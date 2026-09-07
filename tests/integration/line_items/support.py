from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

from psycopg.types.json import Jsonb
from pydantic import TypeAdapter

from lib.auth import AuthService, hash_secret
from lib.auth.request_authority import RequestCredential
from lib.contracts.line_item_authority import LineDecisionRequest
from lib.db.connection import db_connection
from lib.review.line_items.read_repository import candidate_lines, canonical_lines
from lib.review.line_items.service import decide_line


def token_document(doc, scopes):
    token = uuid4().hex
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO api_tokens(user_id,household_id,label,token_hash,scopes) "
            "VALUES(%s,%s,'Line review',%s,%s)",
            (doc.credential.user_id, doc.credential.household_id, hash_secret(token), scopes),
        )
    principal = AuthService().resolve_api_token(token)
    assert principal is not None
    return replace(
        doc, principal=principal, credential=RequestCredential.from_principal(principal)
    ), token


def candidate(doc, description="Reviewed service", *, extraction_id=None, evidence=None):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE document_pages SET text_content=concat_ws(chr(10),text_content,%s::text) "
            "WHERE document_id=%s AND page_number=1",
            (description, doc.document_id),
        )
        if extraction_id is None:
            # A different schema avoids silently superseding earlier proposal fixtures.
            cur.execute(
                "INSERT INTO "
                "document_extractions(document_id,schema_name,schema_version,status,source_engine)"
                "VALUES(%s,%s,'v1','completed','validator') RETURNING id",
                (doc.document_id, f"line-fixture-{description}"),
            )
            extraction_id = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO line_item_candidates
                    (document_id,extraction_id,source_engine,line_item_type,ordinal,description,
                     quantity,net_amount,gross_amount,allowed_amount,plan_paid_amount,currency_code,evidence_json)
                    VALUES(%s,%s,'validator','service_line',1,%s,1.0000,%s,20.0000,0.0000,-3.0001,NULL,%s)
                    RETURNING id""",
            (
                doc.document_id,
                extraction_id,
                description,
                Decimal("99999999999999.9999"),
                Jsonb(
                    evidence
                    if evidence is not None
                    else [{"pageNumber": 1, "sourceEngine": "validator", "sourceText": description}]
                ),
            ),
        )
        return cur.fetchone()["id"]


def source(doc, candidate_id):
    return candidate_lines(
        document_id=doc.document_id, credential=doc.credential, candidate_id=candidate_id
    )["items"][0]


def expected_source(item):
    return {
        "candidateId": item["id"],
        "expectedCandidateVersion": item["candidateVersion"],
        "expectedSourceSnapshotSha256": item["sourceSnapshotSha256"],
        "expectedCandidateDecisionRevision": item["candidateDecisionRevision"],
    }


def create_request(doc, candidate_id, *, ordinal=1):
    item = source(doc, candidate_id)
    return TypeAdapter(LineDecisionRequest).validate_python(
        {
            "operation": "create",
            "source": expected_source(item),
            "target": {
                "lineItemType": "service_line",
                "ordinal": ordinal,
                "canonicalLineItemId": None,
                "expectedCanonicalUpdatedAt": None,
                "expectedLineDecisionRevision": None,
            },
        }
    )


def target(doc, canonical_id):
    envelope = canonical_lines(document_id=doc.document_id, credential=doc.credential)
    item = next(row for row in envelope.items if row.id == canonical_id)
    decision = next(
        (row for row in envelope.decisions if row.canonical_line_item_id == canonical_id), None
    )
    return {
        "lineItemType": item.line_item_type,
        "ordinal": item.ordinal,
        "canonicalLineItemId": item.id,
        "expectedCanonicalUpdatedAt": item.updated_at,
        "expectedLineDecisionRevision": decision.revision if decision else None,
    }


def decide(doc, request):
    if isinstance(request, dict):
        request = TypeAdapter(LineDecisionRequest).validate_python(request)
    return decide_line(document_id=doc.document_id, credential=doc.credential, request=request)


def snapshot(doc):
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT
        (SELECT jsonb_agg(to_jsonb(c) ORDER BY c.id) FROM canonical_line_items c WHERE
        c.document_id=%s) canonical,
        (SELECT jsonb_agg(to_jsonb(c) ORDER BY c.id) FROM line_item_candidates c WHERE
        c.document_id=%s) candidates,
        (SELECT jsonb_agg(to_jsonb(c) ORDER BY c.id) FROM line_item_candidate_decisions c
        WHERE c.document_id=%s) candidate_decisions,
        (SELECT jsonb_agg(to_jsonb(c) ORDER BY c.id) FROM canonical_line_item_decisions c
        WHERE c.document_id=%s) decisions,
        (SELECT jsonb_agg(to_jsonb(c) ORDER BY c.source_candidate_id) FROM
        canonical_line_item_source_bindings c WHERE c.document_id=%s) bindings,
        (SELECT jsonb_agg(to_jsonb(c) ORDER BY c.id) FROM line_item_decision_events c
        WHERE c.document_id=%s) history,
        (SELECT jsonb_agg(to_jsonb(c) ORDER BY c.id) FROM review_events c WHERE
        c.document_id=%s) events,
        (SELECT jsonb_agg(to_jsonb(c) ORDER BY c.id) FROM review_tasks c WHERE
        c.document_id=%s) tasks,
        (SELECT to_jsonb(c) FROM document_fact_projection_state c WHERE c.document_id=%s)
        projection,
        (SELECT jsonb_agg(to_jsonb(c) ORDER BY c.id) FROM document_chunks c WHERE
        c.document_id=%s) chunks,
        (SELECT jsonb_agg(to_jsonb(c) ORDER BY c.id) FROM pipeline_jobs c WHERE
        c.document_id=%s) jobs""",
            (doc.document_id,) * 11,
        )
        return cur.fetchone()
