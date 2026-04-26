from __future__ import annotations

from typing import Any

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from lib.contracts import SavedSearch, SavedSearchWrite
from lib.db.connection import db_connection
from lib.documents.access_policy import DocumentAccessContext


class SavedSearchError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def list_saved_searches(access: DocumentAccessContext) -> list[SavedSearch]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, query_text, filters_json, sort_json, created_at
                FROM saved_searches
                WHERE household_id = %s
                  AND is_active
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 100
                """,
                (access.household_id,),
            )
            rows = cur.fetchall()
    return [_saved_search_from_row(row) for row in rows]


def create_saved_search(
    payload: SavedSearchWrite,
    *,
    access: DocumentAccessContext,
    owner_user_id: object,
) -> SavedSearch:
    try:
        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO saved_searches
                      (household_id, owner_user_id, name, query_text, filters_json, sort_json)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb)
                    ON CONFLICT (household_id, lower(name))
                    WHERE household_id IS NOT NULL AND is_active
                    DO UPDATE SET
                      query_text = EXCLUDED.query_text,
                      filters_json = EXCLUDED.filters_json,
                      sort_json = EXCLUDED.sort_json,
                      updated_at = now()
                    RETURNING id, name, query_text, filters_json, sort_json, created_at
                    """,
                    (
                        access.household_id,
                        owner_user_id,
                        payload.name,
                        payload.query,
                        Jsonb(payload.filters),
                        Jsonb(payload.sort),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
    except UniqueViolation as exc:
        raise SavedSearchError(409, "Saved search name already exists.") from exc
    if not row:
        raise SavedSearchError(500, "Saved search was not created.")
    return _saved_search_from_row(row)


def _saved_search_from_row(row: dict[str, Any]) -> SavedSearch:
    return SavedSearch.model_validate(
        {
            "id": row["id"],
            "name": row["name"],
            "queryText": row["query_text"],
            "filters": row.get("filters_json") or {},
            "sort": row.get("sort_json") or {},
            "createdAt": row["created_at"],
        }
    )
