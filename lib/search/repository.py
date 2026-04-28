from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, LiteralString, cast
from uuid import UUID

from psycopg import Error as PsycopgError
from psycopg import sql

from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext, document_read_access_params
from lib.relationships.visibility_sql import READABLE_COUNTERPART_SQL, readable_counterpart_params
from lib.search.embedding_gateway import vector_literal
from lib.search.query import SearchFilters


@dataclass(frozen=True)
class SearchCandidateRow:
    document_id: UUID
    title: str
    family: str
    rank: int
    source: str
    source_score: float
    snippet: str | None
    matched_chunk_id: UUID | None
    page_number: int | None
    counterparty_display: str | None
    document_date: object | None
    amount_total: float | None
    folder_paths: list[str]
    tags: list[str]


def lexical_search(
    *,
    access: DocumentAccessContext,
    query: str,
    filters: SearchFilters,
    limit: int,
) -> list[SearchCandidateRow]:
    try:
        return _lexical_bm25_search(access=access, query=query, filters=filters, limit=limit)
    except PsycopgError:
        return _lexical_fallback_search(access=access, query=query, filters=filters, limit=limit)


def _search_sql(
    template: LiteralString,
    *,
    where_sql: str,
    readable_counterpart_sql: str = "",
) -> Any:
    # where_sql is assembled only from fixed predicates in _document_filter_sql.
    return sql.SQL(template).format(
        where_sql=sql.SQL(cast(LiteralString, where_sql)),
        readable_counterpart_sql=sql.SQL(cast(LiteralString, readable_counterpart_sql)),
    )


def semantic_search(
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
    where_sql, params = _document_filter_sql(filters, access)
    vector = vector_literal(query_vector)
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                _search_sql(
                    """
                WITH ranked AS (
                  SELECT
                    e.owner_id AS matched_chunk_id,
                    e.document_id,
                    e.embedding <=> %s::vector AS distance
                  FROM embeddings e
                  JOIN document_chunks c ON c.id = e.owner_id AND e.owner_type = 'chunk'
                  JOIN documents d ON d.id = e.document_id
                  LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
                  WHERE e.is_active
                    AND e.modality = 'text'
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
                    'semantic'::text AS source,
                    GREATEST(0, 1 - ranked.distance)::double precision AS source_score,
                    _safe_snippet(COALESCE(c.bm25_text, c.text_content, d.title), %s) AS snippet,
                    c.id AS matched_chunk_id,
                    c.page_start AS page_number,
                    d.counterparty_display,
                    d.document_date,
                    a.total_amount AS amount_total,
                    _folder_paths(d.id) AS folder_paths,
                    _tag_names(d.id) AS tags
                  FROM ranked
                  JOIN document_chunks c ON c.id = ranked.matched_chunk_id
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


def facet_counts(
    *,
    access: DocumentAccessContext,
    filters: SearchFilters,
) -> dict[str, dict[str, int]]:
    where_sql, params = _document_filter_sql(filters, access)
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                _search_sql(
                    """
                SELECT d.document_family::text AS value, count(*) AS total
                FROM documents d
                LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
                WHERE {where_sql}
                GROUP BY d.document_family::text
                ORDER BY total DESC, value
                LIMIT 20
                """,
                    where_sql=where_sql,
                ),
                params,
            )
            family_rows = cur.fetchall()
            cur.execute(
                _search_sql(
                    """
                SELECT COALESCE(f.path_cache, '/' || f.name) AS value, count(DISTINCT d.id) AS total
                FROM documents d
                JOIN document_folder_memberships dfm ON dfm.document_id = d.id
                JOIN folders f ON f.id = dfm.folder_id
                LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
                WHERE {where_sql}
                GROUP BY COALESCE(f.path_cache, '/' || f.name)
                ORDER BY total DESC, value
                LIMIT 20
                """,
                    where_sql=where_sql,
                ),
                params,
            )
            folder_rows = cur.fetchall()
            cur.execute(
                _search_sql(
                    """
                SELECT t.name::text AS value, count(DISTINCT d.id) AS total
                FROM documents d
                JOIN document_tags dt ON dt.document_id = d.id
                JOIN tags t ON t.id = dt.tag_id
                LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
                WHERE {where_sql}
                GROUP BY t.name::text
                ORDER BY total DESC, lower(t.name::text)
                LIMIT 20
                """,
                    where_sql=where_sql,
                ),
                params,
            )
            tag_rows = cur.fetchall()
            cur.execute(
                _search_sql(
                    """
                SELECT d.review_status::text AS value, count(*) AS total
                FROM documents d
                LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
                WHERE {where_sql}
                GROUP BY d.review_status::text
                ORDER BY total DESC, value
                LIMIT 20
                """,
                    where_sql=where_sql,
                ),
                params,
            )
            review_rows = cur.fetchall()
            cur.execute(
                _search_sql(
                    """
                SELECT d.sensitivity::text AS value, count(*) AS total
                FROM documents d
                LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
                WHERE {where_sql}
                GROUP BY d.sensitivity::text
                ORDER BY total DESC, value
                LIMIT 20
                """,
                    where_sql=where_sql,
                ),
                params,
            )
            sensitivity_rows = cur.fetchall()
            cur.execute(
                _search_sql(
                    """
                SELECT dr.relationship_type::text AS value, count(DISTINCT d.id) AS total
                FROM documents d
                JOIN document_relationships dr ON d.id IN (dr.from_document_id, dr.to_document_id)
                LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
                WHERE dr.status <> 'rejected'
                  {readable_counterpart_sql}
                  AND {where_sql}
                GROUP BY dr.relationship_type::text
                ORDER BY total DESC, value
                LIMIT 20
                """,
                    where_sql=where_sql,
                    readable_counterpart_sql=READABLE_COUNTERPART_SQL,
                ),
                [*readable_counterpart_params(access), *params],
            )
            relationship_rows = cur.fetchall()
            cur.execute(
                _search_sql(
                    """
                SELECT dd.deadline_type::text AS value, count(DISTINCT d.id) AS total
                FROM documents d
                JOIN document_deadlines dd ON dd.document_id = d.id
                LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
                WHERE dd.status IN ('open', 'due_soon', 'overdue', 'needs_review')
                  AND {where_sql}
                GROUP BY dd.deadline_type::text
                ORDER BY total DESC, value
                LIMIT 20
                """,
                    where_sql=where_sql,
                ),
                params,
            )
            deadline_rows = cur.fetchall()
            cur.execute(
                _search_sql(
                    """
                SELECT to_char(date_trunc('month', d.document_date::timestamp), 'YYYY-MM') AS value,
                       count(*) AS total
                FROM documents d
                LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
                WHERE {where_sql}
                  AND d.document_date IS NOT NULL
                GROUP BY date_trunc('month', d.document_date::timestamp)
                ORDER BY value DESC
                LIMIT 24
                """,
                    where_sql=where_sql,
                ),
                params,
            )
            date_bucket_rows = cur.fetchall()
    return {
        "families": _facet_map(family_rows),
        "folders": _facet_map(folder_rows),
        "tags": _facet_map(tag_rows),
        "reviewStatus": _facet_map(review_rows),
        "sensitivity": _facet_map(sensitivity_rows),
        "relationshipTypes": _facet_map(relationship_rows),
        "deadlineTypes": _facet_map(deadline_rows),
        "dateBuckets": _facet_map(date_bucket_rows),
    }


def _lexical_bm25_search(
    *,
    access: DocumentAccessContext,
    query: str,
    filters: SearchFilters,
    limit: int,
) -> list[SearchCandidateRow]:
    where_sql, params = _document_filter_sql(filters, access)
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                _search_sql(
                    """
                SELECT *
                FROM (
                  SELECT
                    d.id AS document_id,
                    d.title,
                    d.document_family::text AS family,
                    ROW_NUMBER() OVER (ORDER BY pdb.score(c.id) DESC, d.created_at DESC) AS rank,
                    'lexical'::text AS source,
                    pdb.score(c.id)::double precision AS source_score,
                    COALESCE(
                      pdb.snippet(c.bm25_text),
                      _safe_snippet(COALESCE(c.bm25_text, c.text_content, d.title), %s)
                    ) AS snippet,
                    c.id AS matched_chunk_id,
                    c.page_start AS page_number,
                    d.counterparty_display,
                    d.document_date,
                    a.total_amount AS amount_total,
                    _folder_paths(d.id) AS folder_paths,
                    _tag_names(d.id) AS tags
                  FROM document_chunks c
                  JOIN documents d ON d.id = c.document_id
                  LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
                  WHERE c.bm25_text ||| %s
                    AND {where_sql}
                ) result
                ORDER BY rank
                LIMIT %s
                """,
                    where_sql=where_sql,
                ),
                (query, query, *params, limit),
            )
            rows = cur.fetchall()
    return [_candidate_from_row(row) for row in rows]


def _lexical_fallback_search(
    *,
    access: DocumentAccessContext,
    query: str,
    filters: SearchFilters,
    limit: int,
) -> list[SearchCandidateRow]:
    where_sql, params = _document_filter_sql(filters, access)
    like_query = f"%{query}%"
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                _search_sql(
                    """
                SELECT *
                FROM (
                  SELECT
                    d.id AS document_id,
                    d.title,
                    d.document_family::text AS family,
                    ROW_NUMBER() OVER (
                      ORDER BY
                        ts_rank_cd(
                          to_tsvector('simple', COALESCE(c.bm25_text, c.text_content, d.title)),
                          plainto_tsquery('simple', %s)
                        ) DESC,
                        d.created_at DESC
                    ) AS rank,
                    'lexical'::text AS source,
                    ts_rank_cd(
                      to_tsvector('simple', COALESCE(c.bm25_text, c.text_content, d.title)),
                      plainto_tsquery('simple', %s)
                    )::double precision AS source_score,
                    _safe_snippet(COALESCE(c.bm25_text, c.text_content, d.title), %s) AS snippet,
                    c.id AS matched_chunk_id,
                    c.page_start AS page_number,
                    d.counterparty_display,
                    d.document_date,
                    a.total_amount AS amount_total,
                    _folder_paths(d.id) AS folder_paths,
                    _tag_names(d.id) AS tags
                  FROM document_chunks c
                  JOIN documents d ON d.id = c.document_id
                  LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
                  WHERE (
                    to_tsvector('simple', COALESCE(c.bm25_text, c.text_content, d.title))
                      @@ plainto_tsquery('simple', %s)
                    OR COALESCE(c.bm25_text, c.text_content, d.title) ILIKE %s
                  )
                    AND {where_sql}
                ) result
                ORDER BY rank
                LIMIT %s
                """,
                    where_sql=where_sql,
                ),
                (query, query, query, query, like_query, *params, limit),
            )
            rows = cur.fetchall()
    return [_candidate_from_row(row) for row in rows]


def document_filter_sql(
    filters: SearchFilters,
    access: DocumentAccessContext,
) -> tuple[str, list[object]]:
    clauses = [
        "d.deleted_at IS NULL",
        "document_is_readable(d.id, %s, %s, %s)",
    ]
    params = list(document_read_access_params(access))
    if filters.families:
        clauses.append("d.document_family::text = ANY(%s::text[])")
        params.append(list(filters.families))
    if filters.folder_ids:
        if filters.primary_folder_only:
            clauses.append("d.primary_folder_id = ANY(%s::uuid[])")
        else:
            clauses.append(
                """
                EXISTS (
                  SELECT 1
                  FROM document_folder_memberships search_dfm
                  WHERE search_dfm.document_id = d.id
                    AND search_dfm.folder_id = ANY(%s::uuid[])
                )
                """
            )
        params.append(list(filters.folder_ids))
    if filters.tags:
        clauses.append(
            """
            EXISTS (
              SELECT 1
              FROM document_tags search_dt
              JOIN tags search_t ON search_t.id = search_dt.tag_id
              WHERE search_dt.document_id = d.id
                AND lower(search_t.name::text) = ANY(%s::text[])
            )
            """
        )
        params.append([tag.casefold() for tag in filters.tags])
    if filters.review_statuses:
        clauses.append("d.review_status::text = ANY(%s::text[])")
        params.append(list(filters.review_statuses))
    if filters.reviewed_only is True:
        clauses.append(
            "d.review_status::text IN ('auto_accepted', 'user_confirmed', 'user_corrected')"
        )
    elif filters.reviewed_only is False:
        clauses.append("d.review_status::text NOT IN ('user_confirmed', 'user_corrected')")
    if filters.date_from:
        clauses.append("d.document_date >= %s")
        params.append(filters.date_from)
    if filters.date_to:
        clauses.append("d.document_date <= %s")
        params.append(filters.date_to)
    if filters.amount_min is not None:
        clauses.append("a.total_amount >= %s")
        params.append(filters.amount_min)
    if filters.amount_max is not None:
        clauses.append("a.total_amount <= %s")
        params.append(filters.amount_max)
    if filters.sensitivity:
        clauses.append("d.sensitivity::text = ANY(%s::text[])")
        params.append(list(filters.sensitivity))
    if (
        filters.relationship_types
        or filters.relationship_statuses
        or filters.has_relationships is True
    ):
        clauses.append(
            """
            EXISTS (
              SELECT 1
              FROM document_relationships search_rel
              WHERE d.id IN (search_rel.from_document_id, search_rel.to_document_id)
                AND (%s::text[] IS NULL OR search_rel.relationship_type::text = ANY(%s::text[]))
                AND (
                  (%s::text[] IS NOT NULL AND search_rel.status = ANY(%s::text[]))
                  OR (%s::text[] IS NULL AND search_rel.status <> 'rejected')
                )
                AND document_is_readable(
                  CASE
                    WHEN search_rel.from_document_id = d.id THEN search_rel.to_document_id
                    ELSE search_rel.from_document_id
                  END,
                  %s,
                  %s,
                  %s
                )
            )
            """
        )
        relationship_types = list(filters.relationship_types) or None
        relationship_statuses = list(filters.relationship_statuses) or None
        params.extend(
            [
                relationship_types,
                relationship_types,
                relationship_statuses,
                relationship_statuses,
                relationship_statuses,
                *document_read_access_params(access),
            ]
        )
    elif filters.has_relationships is False:
        clauses.append(
            """
            NOT EXISTS (
              SELECT 1
              FROM document_relationships search_rel
              WHERE d.id IN (search_rel.from_document_id, search_rel.to_document_id)
                AND search_rel.status <> 'rejected'
                AND document_is_readable(
                  CASE
                    WHEN search_rel.from_document_id = d.id THEN search_rel.to_document_id
                    ELSE search_rel.from_document_id
                  END,
                  %s,
                  %s,
                  %s
                )
            )
            """
        )
        params.extend(document_read_access_params(access))
    if filters.deadline_types or filters.deadline_statuses or filters.has_open_deadlines is True:
        clauses.append(
            """
            EXISTS (
              SELECT 1
              FROM document_deadlines search_deadline
              WHERE search_deadline.document_id = d.id
                AND (%s::text[] IS NULL OR search_deadline.deadline_type::text = ANY(%s::text[]))
                AND (
                  (%s::text[] IS NOT NULL AND search_deadline.status = ANY(%s::text[]))
                  OR (
                    %s::text[] IS NULL
                    AND search_deadline.status IN ('open', 'due_soon', 'overdue', 'needs_review')
                  )
                )
            )
            """
        )
        deadline_types = list(filters.deadline_types) or None
        deadline_statuses = list(filters.deadline_statuses) or None
        params.extend(
            [
                deadline_types,
                deadline_types,
                deadline_statuses,
                deadline_statuses,
                deadline_statuses,
            ]
        )
    elif filters.has_open_deadlines is False:
        clauses.append(
            """
            NOT EXISTS (
              SELECT 1
              FROM document_deadlines search_deadline
              WHERE search_deadline.document_id = d.id
                AND search_deadline.status IN ('open', 'due_soon', 'overdue', 'needs_review')
            )
            """
        )
    return "\n  AND ".join(clauses), params


def _document_filter_sql(
    filters: SearchFilters,
    access: DocumentAccessContext,
) -> tuple[str, list[object]]:
    return document_filter_sql(filters, access)


def _candidate_from_row(row: dict[str, Any]) -> SearchCandidateRow:
    return SearchCandidateRow(
        document_id=cast(UUID, row["document_id"]),
        title=str(row["title"]),
        family=str(row["family"]),
        rank=int(row["rank"]),
        source=str(row["source"]),
        source_score=float(row["source_score"] or 0.0),
        snippet=str(row["snippet"]) if row.get("snippet") else None,
        matched_chunk_id=cast(UUID | None, row.get("matched_chunk_id")),
        page_number=int(row["page_number"]) if row.get("page_number") else None,
        counterparty_display=(
            str(row["counterparty_display"]) if row.get("counterparty_display") else None
        ),
        document_date=row.get("document_date"),
        amount_total=float(row["amount_total"]) if row.get("amount_total") is not None else None,
        folder_paths=_string_list(row.get("folder_paths")),
        tags=_string_list(row.get("tags")),
    )


def _facet_map(rows: Sequence[dict[str, object]]) -> dict[str, int]:
    return {str(row["value"]): int(cast(int, row["total"])) for row in rows if row.get("value")}


def _string_list(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return []
