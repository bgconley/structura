from __future__ import annotations

import json
import re
from uuid import UUID

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
FOLDER_ACL_MODES = {"private", "household", "custom"}


class OrganizationError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def organization_error(status_code: int, detail: str) -> OrganizationError:
    return OrganizationError(status_code=status_code, detail=detail)


def normalize_folder_name(value: str) -> str:
    name = " ".join(value.strip().split())
    if not name:
        raise organization_error(422, "Folder name required")
    if "/" in name:
        raise organization_error(422, "Folder names cannot contain slash characters")
    if len(name) > 120:
        raise organization_error(422, "Folder name is too long")
    return name


def normalize_tag_name(value: str) -> str:
    name = " ".join(value.strip().split())
    if not name:
        raise organization_error(422, "Tag name required")
    if len(name) > 80:
        raise organization_error(422, "Tag name is too long")
    return name


def normalize_tag_names(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        name = normalize_tag_name(value)
        key = name.casefold()
        if key not in seen:
            seen.add(key)
            normalized.append(name)
    return normalized


def normalize_document_title(value: str | None) -> str:
    title = " ".join((value or "").strip().split())
    if not title:
        raise organization_error(422, "Title required")
    if len(title) > 240:
        raise organization_error(422, "Title is too long")
    return title


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def normalize_color_hex(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    color = value.strip()
    if not HEX_COLOR_RE.match(color):
        raise organization_error(422, "colorHex must be a six-digit hex color")
    return color.upper()


def validate_acl_mode(value: str | None) -> str:
    acl_mode = value or "household"
    if acl_mode not in FOLDER_ACL_MODES:
        raise organization_error(422, "Invalid ACL mode")
    return acl_mode


def validate_saved_query(
    folder_kind: str,
    value: dict[str, object] | None,
) -> dict[str, object] | None:
    if folder_kind == "manual":
        if value:
            raise organization_error(422, "savedQuery is only supported for smart folders")
        return None
    saved_query = value or {}
    try:
        encoded = json.dumps(saved_query, sort_keys=True)
    except TypeError as exc:
        raise organization_error(422, "savedQuery must be JSON serializable") from exc
    if len(encoded) > 4096:
        raise organization_error(422, "savedQuery is too large for Phase 2")
    _validate_saved_query_value(saved_query)
    return saved_query


def folder_path(parent_path: str | None, name: str) -> str:
    if not parent_path:
        return f"/{name}"
    return f"{parent_path.rstrip('/')}/{name}"


def ltree_from_path(path: str) -> str:
    labels: list[str] = []
    for segment in path.split("/"):
        if not segment:
            continue
        label = re.sub(r"[^a-z0-9_]+", "_", segment.casefold()).strip("_")
        if not label:
            label = "folder"
        if label[0].isdigit():
            label = f"n_{label}"
        labels.append(label[:48])
    return ".".join(labels) or "root"


def dedupe_uuids(values: list[UUID]) -> list[UUID]:
    deduped: list[UUID] = []
    seen: set[UUID] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _validate_saved_query_value(value: object, depth: int = 0) -> None:
    if depth > 4:
        raise organization_error(422, "savedQuery is too deeply nested")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or len(key) > 80:
                raise organization_error(422, "savedQuery keys must be short strings")
            _validate_saved_query_value(child, depth + 1)
        return
    if isinstance(value, list):
        if len(value) > 50:
            raise organization_error(422, "savedQuery arrays are too large for Phase 2")
        for child in value:
            _validate_saved_query_value(child, depth + 1)
        return
    if value is None or isinstance(value, str | int | float | bool):
        return
    raise organization_error(422, "savedQuery contains unsupported values")
