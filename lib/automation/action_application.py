from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.auth import AuthPrincipal
from lib.automation.errors import AutomationError
from lib.automation.repository import record_audit
from lib.contracts import DocumentOrganizationWrite
from lib.documents.access_policy import DocumentAccessContext, document_read_access_params
from lib.organization.document_organization import (
    document_access_context,
    update_document_organization_with_cursor,
)
from lib.organization.policy import OrganizationError
from lib.search.projection import refresh_projection_and_enqueue_embedding


@dataclass(frozen=True)
class RuleActionApplication:
    document_id: UUID
    household_id: UUID
    applied_actions: list[dict[str, Any]]
    refresh_projection: bool


def apply_rule_actions_with_cursor(
    *,
    cur: Any,
    document_id: UUID,
    actions: list[dict[str, Any]],
    principal: AuthPrincipal,
) -> RuleActionApplication:
    access = document_access_context(principal)
    state = _locked_document_state(cur, document_id=document_id, access=access)
    if not state:
        raise AutomationError(404, "Document not found")

    current_folders = list(_uuid_list(state.get("folder_ids")))
    primary_folder = _optional_uuid(state.get("primary_folder_id"))
    current_tags = list(_string_list(state.get("tags")))
    applied: list[dict[str, Any]] = []
    organization_changed = False
    metadata_changed = False

    for action in actions:
        action_type = str(action["type"])
        if action_type == "add_folder":
            folder_id = _action_folder_id(action)
            if folder_id and folder_id not in current_folders:
                current_folders.append(folder_id)
                primary_folder = primary_folder or folder_id
                organization_changed = True
            applied.append(dict(action))
        elif action_type == "set_primary_folder":
            folder_id = _action_folder_id(action)
            if folder_id:
                if folder_id not in current_folders:
                    current_folders.append(folder_id)
                if primary_folder != folder_id:
                    organization_changed = True
                primary_folder = folder_id
            applied.append(dict(action))
        elif action_type == "add_tag":
            tag = str(action["tag"])
            if tag not in current_tags:
                current_tags.append(tag)
                organization_changed = True
            applied.append(dict(action))
        elif action_type == "set_sensitivity":
            metadata_changed = (
                _set_sensitivity(cur, document_id=document_id, value=str(action["value"]))
                or metadata_changed
            )
            applied.append(dict(action))
        elif action_type == "set_document_type":
            metadata_changed = (
                _set_document_type(cur, document_id=document_id, value=str(action["value"]))
                or metadata_changed
            )
            applied.append(dict(action))
        elif action_type == "create_review_task":
            _create_review_task(
                cur,
                document_id=document_id,
                reason=str(action.get("value") or "Review suggested filing."),
                action=action,
            )
            applied.append(dict(action))

    if organization_changed:
        try:
            organization_result = update_document_organization_with_cursor(
                cur=cur,
                document_id=document_id,
                payload=DocumentOrganizationWrite.model_validate(
                    {
                        "folderIds": current_folders,
                        "primaryFolderId": primary_folder,
                        "tags": current_tags,
                    }
                ),
                principal=principal,
            )
        except OrganizationError as exc:
            raise AutomationError(exc.status_code, exc.detail) from exc
    else:
        organization_result = None

    if metadata_changed:
        record_audit(
            cur,
            entity_type="document",
            entity_id=document_id,
            document_id=document_id,
            event_name="filing_rule.metadata_updated",
            actor_label=principal.email,
            payload={
                "appliedActions": [
                    action
                    for action in applied
                    if action["type"] in {"set_sensitivity", "set_document_type"}
                ]
            },
        )

    return RuleActionApplication(
        document_id=document_id,
        household_id=access.household_id,
        applied_actions=applied,
        refresh_projection=metadata_changed
        or bool(organization_result and organization_result.changed),
    )


def refresh_rule_action_projection(application: RuleActionApplication | None) -> None:
    if not application or not application.refresh_projection:
        return
    refresh_projection_and_enqueue_embedding(
        document_id=application.document_id,
        household_id=application.household_id,
        force_reembed=False,
    )


def _locked_document_state(
    cur: Any,
    *,
    document_id: UUID,
    access: DocumentAccessContext,
) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT
          d.id,
          d.primary_folder_id,
          d.document_family::text AS document_family,
          d.sensitivity::text AS sensitivity,
          COALESCE((
            SELECT array_agg(dfm.folder_id ORDER BY dfm.created_at, dfm.folder_id)
            FROM document_folder_memberships dfm
            WHERE dfm.document_id = d.id
          ), ARRAY[]::uuid[]) AS folder_ids,
          COALESCE((
            SELECT array_agg(t.name::text ORDER BY lower(t.name::text), t.id)
            FROM document_tags dt
            JOIN tags t ON t.id = dt.tag_id
            WHERE dt.document_id = d.id
          ), ARRAY[]::text[]) AS tags
        FROM documents d
        WHERE d.id = %s
          AND d.deleted_at IS NULL
          AND document_is_readable(d.id, %s, %s, %s)
        FOR UPDATE
        """,
        (document_id, *document_read_access_params(access)),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _set_sensitivity(cur: Any, *, document_id: UUID, value: str) -> bool:
    cur.execute(
        """
        UPDATE documents
        SET sensitivity = %s::sensitivity_enum,
            updated_at = now()
        WHERE id = %s
          AND sensitivity <> %s::sensitivity_enum
        """,
        (value, document_id, value),
    )
    return bool(cur.rowcount)


def _set_document_type(cur: Any, *, document_id: UUID, value: str) -> bool:
    cur.execute(
        """
        UPDATE documents
        SET document_family = %s::document_family_enum,
            updated_at = now()
        WHERE id = %s
          AND document_family <> %s::document_family_enum
        """,
        (value, document_id, value),
    )
    return bool(cur.rowcount)


def _create_review_task(
    cur: Any,
    *,
    document_id: UUID,
    reason: str,
    action: dict[str, Any],
) -> None:
    cur.execute(
        """
        INSERT INTO review_tasks (document_id, task_type, status, priority, reason, metadata_json)
        SELECT %s, 'automation_rule', 'open', 60, %s, %s::jsonb
        WHERE NOT EXISTS (
          SELECT 1
          FROM review_tasks
          WHERE document_id = %s
            AND task_type = 'automation_rule'
            AND status = 'open'
            AND reason = %s
        )
        """,
        (
            document_id,
            reason,
            Jsonb({"action": action}),
            document_id,
            reason,
        ),
    )


def _action_folder_id(action: dict[str, Any]) -> UUID | None:
    value = action.get("folder_id") or action.get("folderId")
    return _optional_uuid(value)


def _optional_uuid(value: object) -> UUID | None:
    if value is None:
        return None
    return value if isinstance(value, UUID) else UUID(str(value))


def _uuid_list(value: object) -> list[UUID]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item if isinstance(item, UUID) else UUID(str(item)) for item in value]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value]
