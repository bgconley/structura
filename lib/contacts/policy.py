from __future__ import annotations

import re

CONTACT_TYPES = {
    "person",
    "organization",
    "merchant",
    "provider",
    "payer",
    "insurer",
    "law_firm",
    "government",
    "utility",
    "vendor",
    "other",
}

_NON_WORD_RE = re.compile(r"[^\w\s]+", re.UNICODE)


class ContactError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def contact_error(status_code: int, detail: str) -> ContactError:
    return ContactError(status_code=status_code, detail=detail)


def normalize_display_name(value: str) -> str:
    name = " ".join(value.strip().split())
    if not name:
        raise contact_error(422, "displayName is required")
    if len(name) > 240:
        raise contact_error(422, "displayName is too long")
    return name


def normalize_contact_name(value: str) -> str:
    name = normalize_display_name(value)
    name = _NON_WORD_RE.sub(" ", name.casefold())
    return " ".join(name.split())


def normalize_contact_type(value: str) -> str:
    contact_type = (value or "organization").strip()
    if contact_type not in CONTACT_TYPES:
        raise contact_error(422, "Unsupported contactType")
    return contact_type


def normalize_aliases(values: list[str]) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for value in values:
        alias = normalize_display_name(value)
        key = alias.casefold()
        if key not in seen:
            aliases.append(alias)
            seen.add(key)
    return aliases
