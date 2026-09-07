"""Compact exact-generation snapshots under the live document read policy."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import UUID

from lib.auth.authorization_policy import permits_action
from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext, document_read_access_params
from lib.evidence.errors import EvidenceUnavailable


def read_generation(
    document_id: UUID,
    parse_generation_id: UUID,
    access: DocumentAccessContext,
    *,
    offset: int = 0,
    limit: int = 1,
    include_content: bool = False,
) -> dict[str, Any]:
    """Historical reads never require a current run, creator, claim or renderer.

    The statement snapshot includes live ACL/token scope state. Metadata transfers
    only the selected compact descriptors; a page read transfers only that page's
    checkpoint/chunks. Immutable stored content is never re-normalized here.
    """
    if offset < 0 or not 1 <= limit <= 100 or (include_content and limit != 1):
        raise ValueError("Evidence pagination is outside the supported bounds.")
    with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
        cur.execute("SET LOCAL statement_timeout = '10s'")
        cur.execute("SET LOCAL lock_timeout = '2s'")
        cur.execute(
            """SELECT r.id AS processing_run_id,r.document_id,r.parse_generation_id,
              r.original_asset_id,r.original_sha256,r.config_json,r.config_sha256,
              r.status AS run_status,g.inventory_sha256,g.structure_sha256,
              g.structure_json->>'schema_version' AS structure_version,
              jsonb_array_length(g.inventory_json->'pages') AS page_count,
              s.state AS render_set_state,s.expected_sha256 AS render_set_sha256,
              hm.role AS current_household_role,token.scopes AS current_token_scopes,
              clock_timestamp() AS observed_at,
              COALESCE((SELECT jsonb_agg(jsonb_build_object(
                'page_number',c.page_number,'page_id',c.page_id,
                'source_page',g.inventory_json->'pages'->(c.page_number-1),
                'parse_state',c.page_json->>'state',
                'raster',(c.page_json->'source')-
                  ARRAY['native_text','native_text_origin','page_number']::text[],
                'checkpoint_sha256',c.content_sha256,
                'expected_page',s.expected_json->'pages'->(c.page_number-1),
                'asset',a.asset_json,'asset_sha256',a.content_sha256,
                'asset_id',a.id,'asset_page_id',a.page_id,'asset_page_number',a.page_number,
                'page_json',CASE WHEN %s THEN c.page_json END,
                'invocation_json',CASE WHEN %s THEN c.invocation_json END,
                'raw_output',CASE WHEN %s THEN c.raw_output END,
                'chunks',CASE WHEN %s THEN COALESCE((SELECT jsonb_agg(chunk ORDER BY ordinal)
                  FROM jsonb_array_elements(g.structure_json->'chunks') WITH ORDINALITY
                    AS chunks(chunk,ordinal)
                  WHERE (chunk->>'page_number')::integer=c.page_number),'[]'::jsonb) END
                ) ORDER BY c.page_number)
                FROM document_parse_page_checkpoints c
                LEFT JOIN document_parse_page_render_assets a
                  ON a.parse_generation_id=c.parse_generation_id AND a.page_number=c.page_number
                    AND a.page_id=c.page_id AND a.document_id=r.document_id AND a.render_set_id=s.id
                WHERE c.parse_generation_id=g.id AND c.page_number>%s AND c.page_number<=%s
              ),'[]'::jsonb) AS pages
            FROM document_processing_runs r
            JOIN document_parse_generations g ON g.id=r.parse_generation_id
              AND g.document_id=r.document_id AND g.creator_run_id=r.id
            JOIN documents d ON d.id=r.document_id AND d.household_id=r.household_id
            JOIN household_memberships hm ON hm.household_id=d.household_id AND hm.user_id=%s
            LEFT JOIN api_tokens token ON token.id=%s AND token.user_id=hm.user_id
              AND token.household_id=hm.household_id
            LEFT JOIN document_parse_render_sets s ON s.parse_generation_id=g.id
              AND s.document_id=r.document_id AND s.processing_run_id=r.id
            WHERE r.document_id=%s AND g.id=%s AND g.state='sealed'
              AND document_is_readable(d.id,%s,%s,%s)
              AND (%s::uuid IS NULL OR (token.id IS NOT NULL AND token.revoked_at IS NULL
                AND (token.expires_at IS NULL OR token.expires_at>clock_timestamp())))""",
            (
                include_content,
                include_content,
                include_content,
                include_content,
                offset,
                offset + limit,
                access.user_id,
                access.api_token_id,
                document_id,
                parse_generation_id,
                *document_read_access_params(access),
                access.api_token_id,
            ),
        )
        row = cur.fetchone()
        if row is None:
            raise EvidenceUnavailable("Retained generation is unavailable.")
        live = replace(
            access,
            household_role=row["current_household_role"],
            scopes=tuple(row["current_token_scopes"] or ()),
        )
        if not permits_action(live, "documents:read"):
            raise EvidenceUnavailable("Retained generation is unavailable.")
    return row
