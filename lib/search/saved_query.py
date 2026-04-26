from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from lib.search.query import SearchFilters


class SavedQueryError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedSavedQuery:
    filters: SearchFilters


SUPPORTED_KEYS = {
    "amountMax",
    "amountMin",
    "dateFrom",
    "dateTo",
    "document_family",
    "families",
    "folderIds",
    "folder_ids",
    "open_review_tasks",
    "primaryFolderOnly",
    "primary_folder_only",
    "reviewStatuses",
    "review_status",
    "reviewedOnly",
    "reviewed_only",
    "sensitivity",
    "tag_names",
    "tags",
}


def parse_saved_query(value: dict[str, object] | None) -> ParsedSavedQuery:
    saved_query = value or {}
    if not isinstance(saved_query, dict):
        raise SavedQueryError("savedQuery must be a JSON object")
    unsupported = sorted(set(saved_query) - SUPPORTED_KEYS)
    if unsupported:
        raise SavedQueryError(f"Unsupported savedQuery key: {unsupported[0]}")

    review_statuses = _text_values(
        saved_query,
        "reviewStatuses",
        "review_status",
    )
    if _bool_value(saved_query, "open_review_tasks", default=False) and "needs_review" not in {
        status.casefold() for status in review_statuses
    }:
        review_statuses = [*review_statuses, "needs_review"]

    return ParsedSavedQuery(
        filters=SearchFilters(
            families=tuple(_text_values(saved_query, "families", "document_family")),
            folder_ids=tuple(_uuid_values(saved_query, "folderIds", "folder_ids")),
            tags=tuple(_text_values(saved_query, "tags", "tag_names")),
            review_statuses=tuple(review_statuses),
            reviewed_only=_optional_bool(saved_query, "reviewedOnly", "reviewed_only"),
            date_from=_optional_date(saved_query, "dateFrom"),
            date_to=_optional_date(saved_query, "dateTo"),
            amount_min=_optional_decimal(saved_query, "amountMin"),
            amount_max=_optional_decimal(saved_query, "amountMax"),
            sensitivity=tuple(_text_values(saved_query, "sensitivity")),
            primary_folder_only=_bool_value(
                saved_query,
                "primaryFolderOnly",
                "primary_folder_only",
                default=False,
            ),
        )
    )


def _text_values(data: dict[str, object], *keys: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for key in keys:
        raw = data.get(key)
        if raw is None:
            continue
        for item in _as_list(raw, key):
            if not isinstance(item, str):
                raise SavedQueryError(f"savedQuery.{key} must contain strings")
            normalized = item.strip()
            casefolded = normalized.casefold()
            if normalized and casefolded not in seen:
                values.append(normalized)
                seen.add(casefolded)
    return values


def _uuid_values(data: dict[str, object], *keys: str) -> list[UUID]:
    values: list[UUID] = []
    seen: set[UUID] = set()
    for key in keys:
        raw = data.get(key)
        if raw is None:
            continue
        for item in _as_list(raw, key):
            try:
                parsed = item if isinstance(item, UUID) else UUID(str(item))
            except ValueError as exc:
                raise SavedQueryError(f"savedQuery.{key} must contain UUIDs") from exc
            if parsed not in seen:
                values.append(parsed)
                seen.add(parsed)
    return values


def _optional_bool(data: dict[str, object], *keys: str) -> bool | None:
    for key in keys:
        if key in data:
            return _bool_value(data, key)
    return None


def _bool_value(data: dict[str, object], *keys: str, default: bool = False) -> bool:
    for key in keys:
        if key not in data:
            continue
        value = data[key]
        if not isinstance(value, bool):
            raise SavedQueryError(f"savedQuery.{key} must be boolean")
        return value
    return default


def _optional_date(data: dict[str, object], key: str) -> date | None:
    raw = data.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise SavedQueryError(f"savedQuery.{key} must be an ISO date string")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise SavedQueryError(f"savedQuery.{key} must be an ISO date string") from exc


def _optional_decimal(data: dict[str, object], key: str) -> Decimal | None:
    raw = data.get(key)
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise SavedQueryError(f"savedQuery.{key} must be numeric")
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise SavedQueryError(f"savedQuery.{key} must be numeric") from exc


def _as_list(value: object, key: str) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value]
    raise SavedQueryError(f"savedQuery.{key} must be a string or array")
