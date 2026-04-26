from __future__ import annotations

from typing import Any
from uuid import UUID

from lib.auth import AuthPrincipal
from lib.automation import repository, watched_folder_repository
from lib.automation.errors import AutomationError
from lib.automation.watched_folder_policy import (
    WatchedFolderPolicyError,
    normalize_watch_policy,
    validate_watch_path,
)
from lib.config import get_settings
from lib.contracts import ImportStatus, WatchedFolder, WatchedFolderWrite
from lib.db.connection import db_connection


def list_watched_folders(principal: AuthPrincipal) -> list[WatchedFolder]:
    household_id = _require_household(principal)
    with db_connection() as conn:
        with conn.cursor() as cur:
            rows = watched_folder_repository.list_watched_folders(
                cur,
                household_id=household_id,
            )
    return [_watched_folder_from_row(row) for row in rows]


def upsert_watched_folder(payload: WatchedFolderWrite, principal: AuthPrincipal) -> WatchedFolder:
    household_id = _require_household(principal)
    settings = get_settings()
    try:
        resolved_path = validate_watch_path(payload.path, runtime_root=settings.runtime_root)
        policy = normalize_watch_policy(payload.policy)
    except WatchedFolderPolicyError as exc:
        raise AutomationError(422, str(exc)) from exc
    with db_connection() as conn:
        with conn.cursor() as cur:
            _validate_target_folders(cur, policy=policy, principal=principal)
            row = watched_folder_repository.upsert_watched_folder(
                cur,
                folder_id=payload.id,
                household_id=household_id,
                owner_user_id=principal.user_id,
                path=str(resolved_path),
                enabled=payload.enabled,
                policy_json=policy,
            )
            if not row:
                raise AutomationError(404, "Watched folder not found")
            repository.record_audit(
                cur,
                entity_type="watched_folder",
                entity_id=_uuid(row["id"]),
                event_name="watched_folder.upserted",
                actor_label=principal.email,
                payload={"path": str(resolved_path), "enabled": payload.enabled},
            )
        conn.commit()
    return _watched_folder_from_row(row)


def list_import_status(principal: AuthPrincipal) -> list[ImportStatus]:
    household_id = _require_household(principal)
    with db_connection() as conn:
        with conn.cursor() as cur:
            rows = watched_folder_repository.import_status(cur, household_id=household_id)
    return [_import_status_from_row(row) for row in rows]


def _validate_target_folders(
    cur: object,
    *,
    policy: dict[str, Any],
    principal: AuthPrincipal,
) -> None:
    household_id = _require_household(principal)
    writable = repository.writable_folders(
        cur,
        household_id=household_id,
        user_id=principal.user_id,
    )
    writable_ids = {str(row["id"]) for row in writable}
    for folder_id in policy.get("targetFolderIds", []):
        if str(folder_id) not in writable_ids:
            raise AutomationError(422, "Watched-folder target folder is not writable")


def _watched_folder_from_row(row: dict[str, Any]) -> WatchedFolder:
    return WatchedFolder.model_validate(
        {
            "id": row["id"],
            "path": row["path"],
            "enabled": row["enabled"],
            "policy": row.get("policy_json") or {},
            "lastScanAt": row.get("last_scan_at"),
        }
    )


def _import_status_from_row(row: dict[str, Any]) -> ImportStatus:
    policy = row.get("policy_json") or {}
    last_scan = policy.get("lastScan") if isinstance(policy, dict) else {}
    if not isinstance(last_scan, dict):
        last_scan = {}
    return ImportStatus.model_validate(
        {
            "watchedFolderId": row["id"],
            "path": row["path"],
            "enabled": row["enabled"],
            "lastScanAt": row.get("last_scan_at"),
            "acceptedCount": last_scan.get("acceptedCount", 0),
            "rejectedCount": last_scan.get("rejectedCount", 0),
            "skippedCount": last_scan.get("skippedCount", 0),
        }
    )


def _require_household(principal: AuthPrincipal) -> UUID:
    if not principal.household_id:
        raise AutomationError(403, "Household required")
    return principal.household_id


def _uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))
