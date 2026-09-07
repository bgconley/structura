"""Real credential and document-grant fixtures for processing authority tests."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from lib.auth import AuthService
from lib.auth.primitives import hash_secret
from lib.db.connection import db_connection


def token_request(processing, scopes=("documents:write",)):
    secret = str(uuid4())
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO api_tokens (user_id, household_id, label, token_hash, scopes)
            VALUES (%s,%s,'processing-test',%s,%s)""",
            (
                processing.principal.user_id,
                processing.principal.household_id,
                hash_secret(secret),
                list(scopes),
            ),
        )
    principal = AuthService().resolve_api_token(secret)
    assert principal is not None
    return replace(processing, principal=principal)


def make_granted_member(processing):
    """The requester depends on one custom-folder write grant, not ownership."""
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (email,display_name) VALUES (%s,'Other owner') RETURNING id",
            (f"owner-{uuid4()}@example.com",),
        )
        owner_id = cur.fetchone()["id"]
        cur.execute(
            "UPDATE household_memberships SET role='member' WHERE user_id=%s AND household_id=%s",
            (processing.principal.user_id, processing.principal.household_id),
        )
        cur.execute(
            """INSERT INTO folders (name,household_id,owner_user_id,acl_mode)
            VALUES (%s,%s,%s,'custom') RETURNING id""",
            (f"Private shared source {uuid4()}", processing.principal.household_id, owner_id),
        )
        folder_id = cur.fetchone()["id"]
        cur.execute(
            """UPDATE documents SET owner_user_id=%s,primary_folder_id=%s,acl_mode='household'
            WHERE id=%s""",
            (owner_id, folder_id, processing.document_id),
        )
        cur.execute(
            """INSERT INTO folder_acl (folder_id,principal_type,principal_id,permission)
            VALUES (%s,'user',%s,'write') RETURNING id""",
            (folder_id, processing.principal.user_id),
        )
        grant_id = cur.fetchone()["id"]
    return folder_id, grant_id


def revoke(cur, processing, kind, *, grant_id=None):
    if kind == "disabled":
        cur.execute(
            "UPDATE users SET is_disabled=true WHERE id=%s", (processing.principal.user_id,)
        )
    elif kind == "membership_removed":
        cur.execute(
            "DELETE FROM household_memberships WHERE user_id=%s AND household_id=%s",
            (processing.principal.user_id, processing.principal.household_id),
        )
    elif kind == "viewer":
        cur.execute(
            "UPDATE household_memberships SET role='viewer' WHERE user_id=%s AND household_id=%s",
            (processing.principal.user_id, processing.principal.household_id),
        )
    elif kind == "private_document":
        cur.execute(
            "UPDATE documents SET acl_mode='private' WHERE id=%s", (processing.document_id,)
        )
    elif kind == "refiled":
        cur.execute(
            "INSERT INTO folders (name,household_id,acl_mode) VALUES (%s,%s,'private') "
            "RETURNING id",
            (f"Unavailable {uuid4()}", processing.principal.household_id),
        )
        folder_id = cur.fetchone()["id"]
        cur.execute(
            "UPDATE documents SET primary_folder_id=%s WHERE id=%s",
            (folder_id, processing.document_id),
        )
    elif kind == "grant_removed":
        cur.execute("DELETE FROM folder_acl WHERE id=%s", (grant_id,))
    elif kind == "token_revoked":
        cur.execute(
            "UPDATE api_tokens SET revoked_at=clock_timestamp() WHERE id=%s",
            (processing.principal.api_token_id,),
        )
    elif kind == "token_expired":
        cur.execute(
            "UPDATE api_tokens SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s",
            (processing.principal.api_token_id,),
        )
    elif kind == "token_missing":
        cur.execute("DELETE FROM api_tokens WHERE id=%s", (processing.principal.api_token_id,))
    elif kind == "token_read_only":
        cur.execute(
            "UPDATE api_tokens SET scopes=ARRAY['documents:read'] WHERE id=%s",
            (processing.principal.api_token_id,),
        )
    else:
        raise AssertionError(f"Unknown test authority change: {kind}")
