from __future__ import annotations

from uuid import UUID

from lib.contracts import DocumentSummary


def document_summary_from_row(row: dict[str, object]) -> DocumentSummary:
    thumbnail_asset_id = row.get("thumbnail_asset_id")
    return DocumentSummary.model_validate(
        {
            "id": row["id"],
            "title": row["title"],
            "family": row["family"],
            "lifecycleState": row["lifecycle_state"],
            "reviewStatus": row["review_status"],
            "createdAt": row["created_at"],
            "documentDate": row.get("document_date"),
            "amountTotal": row.get("amount_total"),
            "counterpartyDisplay": row.get("counterparty_display"),
            "thumbnailUrl": f"/api/v1/assets/{thumbnail_asset_id}" if thumbnail_asset_id else None,
            "folderPaths": string_list(row.get("folder_paths")),
            "tags": string_list(row.get("tags")),
            "relatedCount": row.get("related_count") or 0,
        }
    )


def uuid_list(value: object) -> list[UUID]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item if isinstance(item, UUID) else UUID(str(item)) for item in value]


def string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value]
