from __future__ import annotations

from typing import Any, LiteralString, cast

from psycopg import Error as PsycopgError
from psycopg import sql

from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext
from lib.search.embedding_gateway import vector_literal
from lib.search.query import SearchFilters
from lib.search.repository import SearchCandidateRow, document_filter_sql


def visual_search(
    *,
    access: DocumentAccessContext,
    query_vector: list[float],
    query: str,
    profile_name: str,
    profile_version: str,
    dimensions: int,
    filters: SearchFilters,
    limit: int,
    oversample: int,
) -> list[SearchCandidateRow]:
    try:
        return _visual_vector_search(
            access=access,
            query_vector=query_vector,
            query=query,
            profile_name=profile_name,
            profile_version=profile_version,
            dimensions=dimensions,
            filters=filters,
            limit=limit,
            oversample=oversample,
        )
    except PsycopgError:
        return []


def _visual_vector_search(
    *,
    access: DocumentAccessContext,
    query_vector: list[float],
    query: str,
    profile_name: str,
    profile_version: str,
    dimensions: int,
    filters: SearchFilters,
    limit: int,
    oversample: int,
) -> list[SearchCandidateRow]:
    where_sql, params = document_filter_sql(filters, access)
    vector = vector_literal(query_vector)
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                _search_sql(
                    """
                WITH ranked AS (
                  SELECT
                    e.owner_id AS matched_page_id,
                    e.document_id,
                    e.embedding <=> %s::vector AS distance
                  FROM embeddings e
                  JOIN document_pages p ON p.id = e.owner_id AND e.owner_type = 'page'
                  JOIN documents d ON d.id = e.document_id
                  LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
                  WHERE e.is_active
                    AND e.modality = 'visual'
                    AND e.model_name = %s
                    AND COALESCE(e.model_version, '') = %s
                    AND e.embedding_dimensions = %s
                    AND {where_sql}
                  ORDER BY e.embedding <=> %s::vector
                  LIMIT %s
                )
                SELECT *
                FROM (
                  SELECT
                    d.id AS document_id,
                    d.title,
                    d.document_family::text AS family,
                    ROW_NUMBER() OVER (ORDER BY ranked.distance ASC, d.created_at DESC) AS rank,
                    'visual'::text AS source,
                    GREATEST(0, 1 - ranked.distance)::double precision AS source_score,
                    _safe_snippet(
                      COALESCE(
                        p.metadata_json #>> '{{phase8,quality,summary}}',
                        p.text_content,
                        d.title
                      ),
                      %s
                    ) AS snippet,
                    NULL::uuid AS matched_chunk_id,
                    p.page_number AS page_number,
                    d.counterparty_display,
                    d.document_date,
                    a.total_amount AS amount_total,
                    _folder_paths(d.id) AS folder_paths,
                    _tag_names(d.id) AS tags
                  FROM ranked
                  JOIN document_pages p ON p.id = ranked.matched_page_id
                  JOIN documents d ON d.id = ranked.document_id
                  LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
                ) result
                ORDER BY rank
                LIMIT %s
                """,
                    where_sql=where_sql,
                ),
                (
                    vector,
                    profile_name,
                    profile_version,
                    dimensions,
                    *params,
                    vector,
                    oversample,
                    query,
                    limit,
                ),
            )
            rows = cur.fetchall()
    return [_candidate_from_row(row) for row in rows]


def _search_sql(template: LiteralString, *, where_sql: str) -> Any:
    return sql.SQL(template).format(where_sql=sql.SQL(cast(LiteralString, where_sql)))


def _candidate_from_row(row: dict[str, Any]) -> SearchCandidateRow:
    return SearchCandidateRow(
        document_id=row["document_id"],
        title=str(row["title"]),
        family=str(row["family"]),
        rank=int(row["rank"]),
        source=str(row["source"]),
        source_score=float(row["source_score"] or 0.0),
        snippet=str(row["snippet"]) if row.get("snippet") else None,
        matched_chunk_id=None,
        page_number=int(row["page_number"]) if row.get("page_number") else None,
        counterparty_display=(
            str(row["counterparty_display"]) if row.get("counterparty_display") else None
        ),
        document_date=row.get("document_date"),
        amount_total=float(row["amount_total"]) if row.get("amount_total") is not None else None,
        folder_paths=_string_list(row.get("folder_paths")),
        tags=_string_list(row.get("tags")),
    )


def _string_list(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return []
