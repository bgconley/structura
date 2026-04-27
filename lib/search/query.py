from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from lib.contracts import SearchRequest


class SearchValidationError(Exception):
    pass


@dataclass(frozen=True)
class SearchFilters:
    families: tuple[str, ...] = ()
    folder_ids: tuple[UUID, ...] = ()
    tags: tuple[str, ...] = ()
    review_statuses: tuple[str, ...] = ()
    reviewed_only: bool | None = None
    date_from: date | None = None
    date_to: date | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    sensitivity: tuple[str, ...] = ()
    relationship_types: tuple[str, ...] = ()
    relationship_statuses: tuple[str, ...] = ()
    has_relationships: bool | None = None
    deadline_types: tuple[str, ...] = ()
    deadline_statuses: tuple[str, ...] = ()
    has_open_deadlines: bool | None = None
    primary_folder_only: bool = False

    @property
    def applied_count(self) -> int:
        return sum(
            [
                bool(self.families),
                bool(self.folder_ids),
                bool(self.tags),
                bool(self.review_statuses),
                self.reviewed_only is not None,
                self.date_from is not None,
                self.date_to is not None,
                self.amount_min is not None,
                self.amount_max is not None,
                bool(self.sensitivity),
                bool(self.relationship_types),
                bool(self.relationship_statuses),
                self.has_relationships is not None,
                bool(self.deadline_types),
                bool(self.deadline_statuses),
                self.has_open_deadlines is not None,
                self.primary_folder_only,
            ]
        )


@dataclass(frozen=True)
class ParsedSearchQuery:
    query: str
    mode: str
    limit: int
    filters: SearchFilters
    include_debug: bool = False
    include_visual: bool = False


def parse_search_request(request: SearchRequest) -> ParsedSearchQuery:
    query = request.query.strip()
    if not query:
        raise SearchValidationError("Search query must not be blank.")
    if request.date_from and request.date_to and request.date_from > request.date_to:
        raise SearchValidationError("dateFrom must be on or before dateTo.")
    if (
        request.amount_min is not None
        and request.amount_max is not None
        and request.amount_min > request.amount_max
    ):
        raise SearchValidationError("amountMin must be less than or equal to amountMax.")
    return ParsedSearchQuery(
        query=query,
        mode=request.mode,
        limit=request.limit,
        include_debug=request.include_debug,
        include_visual=request.include_visual,
        filters=SearchFilters(
            families=tuple(_dedupe_text(request.families)),
            folder_ids=tuple(dict.fromkeys(request.folder_ids)),
            tags=tuple(_dedupe_text(request.tags)),
            review_statuses=tuple(_dedupe_text(request.review_statuses)),
            reviewed_only=request.reviewed_only,
            date_from=request.date_from,
            date_to=request.date_to,
            amount_min=request.amount_min,
            amount_max=request.amount_max,
            sensitivity=tuple(_dedupe_text(request.sensitivity)),
            relationship_types=tuple(_dedupe_text(request.relationship_types)),
            relationship_statuses=tuple(_dedupe_text(request.relationship_statuses)),
            has_relationships=request.has_relationships,
            deadline_types=tuple(_dedupe_text(request.deadline_types)),
            deadline_statuses=tuple(_dedupe_text(request.deadline_statuses)),
            has_open_deadlines=request.has_open_deadlines,
            primary_folder_only=request.primary_folder_only,
        ),
    )


def _dedupe_text(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            result.append(normalized)
            seen.add(key)
    return result
