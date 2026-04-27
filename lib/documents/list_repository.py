from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, LiteralString, TypeVar, cast
from uuid import UUID

from psycopg import sql

from lib.contracts import DocumentSummary
from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext
from lib.documents.summary_mapping import document_summary_from_row
from lib.search.query import SearchFilters
from lib.search.repository import document_filter_sql
from lib.search.saved_query import parse_saved_query

T = TypeVar("T")

DOCUMENT_LIST_SELECT_COLUMNS_SQL = """
  d.id,
  d.title,
  d.document_family::text AS family,
  d.lifecycle_state::text AS lifecycle_state,
  d.review_status::text AS review_status,
  d.created_at,
  d.document_date,
  d.counterparty_display,
  a.total_amount AS amount_total,
  (
    SELECT ta.id
    FROM document_assets ta
    WHERE ta.document_id = d.id
      AND ta.asset_role = 'thumbnail'
      AND ta.is_current
    ORDER BY ta.page_number NULLS LAST, ta.created_at DESC
    LIMIT 1
  ) AS thumbnail_asset_id,
  COALESCE(
    (
      SELECT array_agg(
        COALESCE(f.path_cache, '/' || f.name)
        ORDER BY dfm.is_primary DESC, COALESCE(f.path_cache, '/' || f.name), f.name
      )
      FROM document_folder_memberships dfm
      JOIN folders f ON f.id = dfm.folder_id
      WHERE dfm.document_id = d.id
    ),
    ARRAY[]::text[]
  ) AS folder_paths,
  COALESCE(
    (
      SELECT array_agg(t.name::text ORDER BY lower(t.name::text), t.id)
      FROM document_tags dt
      JOIN tags t ON t.id = dt.tag_id
      WHERE dt.document_id = d.id
    ),
    ARRAY[]::text[]
  ) AS tags,
  (
    SELECT count(*)::int
    FROM document_relationships dr
    WHERE dr.status IN ('suggested', 'confirmed')
      AND d.id IN (dr.from_document_id, dr.to_document_id)
  ) AS related_count
"""

DOCUMENT_LIST_FROM_SQL = """
FROM documents d
LEFT JOIN document_primary_amounts_v a ON a.document_id = d.id
"""

DOCUMENT_LIST_ORDER_SQL = """
ORDER BY d.created_at DESC, d.id DESC
LIMIT %s OFFSET %s
"""


@dataclass(frozen=True)
class DocumentListFilters:
    access: DocumentAccessContext
    query_text: str | None = None
    family: str | None = None
    review_status: str | None = None
    folder_id: UUID | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True)
class _ResolvedFolderFilter:
    available: bool
    filters: SearchFilters | None = None


def list_document_summaries(filters: DocumentListFilters) -> tuple[list[DocumentSummary], int]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            resolved_folder = _resolve_folder_filter(cur, filters)
            if not resolved_folder.available:
                return [], 0
            search_filters = _combined_document_list_filters(filters, resolved_folder.filters)
            if search_filters is None:
                return [], 0
            where_sql, filter_params = _document_list_where_sql(filters, search_filters)
            cur.execute(
                _document_list_count_sql(where_sql),
                filter_params,
            )
            total_row = cur.fetchone()
            cur.execute(
                _document_list_select_sql(where_sql),
                [*filter_params, filters.limit, filters.offset],
            )
            rows = cur.fetchall()

    total = int(total_row["total"] if total_row else 0)
    return [document_summary_from_row(row) for row in rows], total


def _document_list_count_sql(where_sql: str) -> sql.Composed:
    return sql.SQL(
        """
        SELECT count(*) AS total
        {from_sql}
        WHERE {where_sql}
        """
    ).format(
        from_sql=sql.SQL(DOCUMENT_LIST_FROM_SQL),
        where_sql=sql.SQL(cast(LiteralString, where_sql)),
    )


def _document_list_select_sql(where_sql: str) -> sql.Composed:
    return sql.SQL(
        """
        SELECT
        {columns_sql}
        {from_sql}
        WHERE {where_sql}
        {order_sql}
        """
    ).format(
        columns_sql=sql.SQL(DOCUMENT_LIST_SELECT_COLUMNS_SQL),
        from_sql=sql.SQL(DOCUMENT_LIST_FROM_SQL),
        where_sql=sql.SQL(cast(LiteralString, where_sql)),
        order_sql=sql.SQL(DOCUMENT_LIST_ORDER_SQL),
    )


def _document_list_where_sql(
    filters: DocumentListFilters,
    search_filters: SearchFilters,
) -> tuple[str, list[object]]:
    where_sql, params = document_filter_sql(search_filters, filters.access)
    if filters.query_text:
        query_like = f"%{filters.query_text}%"
        where_sql = (
            f"{where_sql}\n  AND ("
            "%s::text IS NULL "
            "OR d.title ILIKE %s "
            "OR d.original_filename ILIKE %s "
            "OR d.counterparty_display ILIKE %s)"
        )
        params.extend([filters.query_text, query_like, query_like, query_like])
    return where_sql, params


def _resolve_folder_filter(cur: Any, filters: DocumentListFilters) -> _ResolvedFolderFilter:
    if not filters.folder_id:
        return _ResolvedFolderFilter(available=True)
    cur.execute(
        """
        SELECT f.folder_kind::text AS folder_kind, f.saved_query_json
        FROM folders f
        WHERE f.id = %s
          AND (f.household_id = %s OR (f.household_id IS NULL AND f.is_system))
          AND (
            f.acl_mode = 'household'
            OR f.owner_user_id = %s
            OR EXISTS (
              SELECT 1
              FROM folder_acl fa
              WHERE fa.folder_id = f.id
                AND fa.permission IN ('read', 'write', 'admin')
                AND (
                  (fa.principal_type = 'user' AND fa.principal_id = %s)
                  OR (fa.principal_type = 'household' AND fa.principal_id = %s)
                )
            )
          )
        """,
        (
            filters.folder_id,
            filters.access.household_id,
            filters.access.user_id,
            filters.access.user_id,
            filters.access.household_id,
        ),
    )
    row = cur.fetchone()
    if not row:
        return _ResolvedFolderFilter(available=False)
    if row["folder_kind"] == "smart":
        return _ResolvedFolderFilter(
            available=True,
            filters=parse_saved_query(row.get("saved_query_json") or {}).filters,
        )
    return _ResolvedFolderFilter(
        available=True,
        filters=SearchFilters(folder_ids=(filters.folder_id,)),
    )


def _combined_document_list_filters(
    filters: DocumentListFilters,
    folder_filters: SearchFilters | None,
) -> SearchFilters | None:
    base = SearchFilters(
        families=(filters.family,) if filters.family else (),
        review_statuses=(filters.review_status,) if filters.review_status else (),
    )
    if not folder_filters:
        return base
    families = _combine_exact_values(base.families, folder_filters.families)
    folder_ids = _combine_exact_values(base.folder_ids, folder_filters.folder_ids)
    review_statuses = _combine_exact_values(
        base.review_statuses,
        folder_filters.review_statuses,
    )
    if families is None or folder_ids is None or review_statuses is None:
        return None
    date_from = _max_date(base.date_from, folder_filters.date_from)
    date_to = _min_date(base.date_to, folder_filters.date_to)
    amount_min = _max_decimal(base.amount_min, folder_filters.amount_min)
    amount_max = _min_decimal(base.amount_max, folder_filters.amount_max)
    if date_from and date_to and date_from > date_to:
        return None
    if amount_min is not None and amount_max is not None and amount_min > amount_max:
        return None
    return SearchFilters(
        families=families,
        folder_ids=folder_ids,
        tags=folder_filters.tags,
        review_statuses=review_statuses,
        reviewed_only=folder_filters.reviewed_only,
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min,
        amount_max=amount_max,
        sensitivity=folder_filters.sensitivity,
        relationship_types=folder_filters.relationship_types,
        relationship_statuses=folder_filters.relationship_statuses,
        has_relationships=folder_filters.has_relationships,
        deadline_types=folder_filters.deadline_types,
        deadline_statuses=folder_filters.deadline_statuses,
        has_open_deadlines=folder_filters.has_open_deadlines,
        primary_folder_only=base.primary_folder_only or folder_filters.primary_folder_only,
    )


def _combine_exact_values(left: tuple[T, ...], right: tuple[T, ...]) -> tuple[T, ...] | None:
    if left and right:
        combined = tuple(value for value in left if value in right)
        return combined or None
    return left or right


def _max_decimal(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    values = [value for value in [left, right] if value is not None]
    return max(values) if values else None


def _min_decimal(left: Decimal | None, right: Decimal | None) -> Decimal | None:
    values = [value for value in [left, right] if value is not None]
    return min(values) if values else None


def _max_date(left: date | None, right: date | None) -> date | None:
    values = [value for value in [left, right] if value is not None]
    return max(values) if values else None


def _min_date(left: date | None, right: date | None) -> date | None:
    values = [value for value in [left, right] if value is not None]
    return min(values) if values else None
