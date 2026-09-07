"""Read one immutable generation under the live document/token read contract."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import UUID

from lib.auth.authorization_policy import permits_action
from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext, document_read_access_params
from lib.evaluation.capture_models import CaptureUnavailable


def read_capture_rows(
    *,
    document_id: UUID,
    processing_run_id: UUID,
    parse_generation_id: UUID,
    access: DocumentAccessContext,
) -> dict[str, Any]:
    """One statement snapshot binds ACL/token state and all captured rows.

    No publication/run locks are needed for immutable sealed history. A later
    permission revocation cannot revoke bytes already returned by an authorized
    read. No filesystem, rendering or model operations occur in this transaction.
    """
    with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
        cur.execute("SET LOCAL statement_timeout = '10s'")
        cur.execute("SET LOCAL lock_timeout = '2s'")
        cur.execute(
            """SELECT r.id AS processing_run_id, r.document_id, r.parse_generation_id,
              r.original_asset_id, r.original_sha256, r.config_json, r.config_sha256,
              r.status AS run_status, g.state AS parse_state, g.creator_run_id,
              g.inventory_json, g.inventory_sha256, g.structure_json, g.structure_sha256,
              g.sealed_at, a.sha256 AS asset_sha256, a.mime_type, a.byte_size,
              hm.role AS current_household_role, token.scopes AS current_token_scopes,
              COALESCE((SELECT jsonb_agg(jsonb_build_object(
                'parse_generation_id', c.parse_generation_id, 'page_number', c.page_number,
                'page_id', c.page_id, 'page_json', c.page_json,
                'invocation_json', c.invocation_json, 'raw_output', c.raw_output,
                'content_sha256', c.content_sha256) ORDER BY c.page_number)
                FROM document_parse_page_checkpoints c WHERE c.parse_generation_id = g.id
              ), '[]'::jsonb) AS checkpoints
            FROM document_processing_runs r
            JOIN document_parse_generations g
              ON g.id = r.parse_generation_id AND g.document_id = r.document_id
              AND g.creator_run_id = r.id
            JOIN documents d ON d.id = r.document_id AND d.household_id = r.household_id
            JOIN household_memberships hm ON hm.household_id = d.household_id AND hm.user_id = %s
            JOIN document_assets a ON a.id = r.original_asset_id
              AND a.document_id = r.document_id AND a.asset_role = 'original'
            LEFT JOIN api_tokens token ON token.id = %s AND token.user_id = hm.user_id
              AND token.household_id = hm.household_id
            WHERE r.document_id = %s AND r.id = %s AND g.id = %s
              AND g.state = 'sealed' AND document_is_readable(d.id, %s, %s, %s)
              AND (%s::uuid IS NULL OR (token.id IS NOT NULL AND token.revoked_at IS NULL
                AND (token.expires_at IS NULL OR token.expires_at > clock_timestamp())))""",
            (
                access.user_id,
                access.api_token_id,
                document_id,
                processing_run_id,
                parse_generation_id,
                *document_read_access_params(access),
                access.api_token_id,
            ),
        )
        row = cur.fetchone()
        if row is None:
            raise CaptureUnavailable("Sealed processing capture is unavailable.")
        # Reuse the central action/scope policy with current persisted token scopes
        # and household role rather than embedding a second scope allowlist in SQL.
        live_access = replace(
            access,
            household_role=row["current_household_role"],
            scopes=tuple(row["current_token_scopes"] or ()),
        )
        if not permits_action(live_access, "documents:read"):
            raise CaptureUnavailable("Sealed processing capture is unavailable.")
    return row
