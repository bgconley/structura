from __future__ import annotations

from typing import Any, TypeAlias, cast
from uuid import UUID

from psycopg.types.json import Jsonb

Row: TypeAlias = dict[str, Any]


def list_watched_folders(cur: Any, *, household_id: UUID) -> list[Row]:
    cur.execute(
        """
        SELECT id, path, enabled, policy_json, last_scan_at
        FROM watched_folders
        WHERE household_id = %s
        ORDER BY enabled DESC, path
        """,
        (household_id,),
    )
    return cast(list[Row], cur.fetchall())


def upsert_watched_folder(
    cur: Any,
    *,
    folder_id: UUID | None,
    household_id: UUID,
    owner_user_id: UUID,
    path: str,
    enabled: bool,
    policy_json: dict[str, Any],
) -> Row | None:
    if folder_id:
        cur.execute(
            """
            UPDATE watched_folders
            SET path = %s,
                enabled = %s,
                policy_json = %s::jsonb,
                owner_user_id = %s,
                updated_at = now()
            WHERE id = %s
              AND household_id = %s
            RETURNING id, path, enabled, policy_json, last_scan_at
            """,
            (path, enabled, Jsonb(policy_json), owner_user_id, folder_id, household_id),
        )
        return cast(Row | None, cur.fetchone())
    cur.execute(
        """
        INSERT INTO watched_folders (household_id, owner_user_id, path, enabled, policy_json)
        VALUES (%s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (household_id, path)
        DO UPDATE SET enabled = EXCLUDED.enabled,
                      policy_json = EXCLUDED.policy_json,
                      owner_user_id = EXCLUDED.owner_user_id,
                      updated_at = now()
        RETURNING id, path, enabled, policy_json, last_scan_at
        """,
        (household_id, owner_user_id, path, enabled, Jsonb(policy_json)),
    )
    return cast(Row | None, cur.fetchone())


def enabled_watched_folders(
    cur: Any,
    *,
    household_id: UUID | None = None,
) -> list[Row]:
    cur.execute(
        """
        SELECT id, household_id, owner_user_id, path, enabled, policy_json, last_scan_at
        FROM watched_folders
        WHERE enabled
          AND (%s::uuid IS NULL OR household_id = %s)
        ORDER BY path
        """,
        (household_id, household_id),
    )
    return cast(list[Row], cur.fetchall())


def update_watched_folder_scan(
    cur: Any,
    *,
    watched_folder_id: UUID,
    accepted: int,
    rejected: int,
    skipped: int,
) -> None:
    cur.execute(
        """
        UPDATE watched_folders
        SET last_scan_at = now(),
            policy_json = policy_json || %s::jsonb,
            updated_at = now()
        WHERE id = %s
        """,
        (
            Jsonb(
                {
                    "lastScan": {
                        "acceptedCount": accepted,
                        "rejectedCount": rejected,
                        "skippedCount": skipped,
                    }
                }
            ),
            watched_folder_id,
        ),
    )


def import_status(cur: Any, *, household_id: UUID) -> list[Row]:
    cur.execute(
        """
        SELECT id, path, enabled, policy_json, last_scan_at
        FROM watched_folders
        WHERE household_id = %s
        ORDER BY last_scan_at DESC NULLS LAST, path
        """,
        (household_id,),
    )
    return cast(list[Row], cur.fetchall())
