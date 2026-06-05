from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from lib.extraction.models import (
    ExtractionSourceDocument,
    ParsedElementText,
    ParsedPageText,
    ParsedTableText,
)


@dataclass(frozen=True)
class DoclingReferenceMaps:
    page_ids_by_ref: dict[str, str]
    element_ids_by_ref: dict[str, str]
    table_ids_by_ref: dict[str, str]

    def resolve_page_id(self, value: str) -> str | None:
        return self.page_ids_by_ref.get(value)

    def resolve_element_id(self, value: str) -> str | None:
        return self.element_ids_by_ref.get(value)

    def resolve_table_id(self, value: str) -> str | None:
        return self.table_ids_by_ref.get(value)


def page_ref(page: ParsedPageText) -> str:
    return f"page-{page.page_number}"


def element_ref(element: ParsedElementText) -> str:
    return f"page-{element.page_number}-element-{element.ordinal}"


def table_ref(table: ParsedTableText) -> str:
    return f"page-{table.page_number}-table-{table.table_index}"


def docling_reference_maps(source: ExtractionSourceDocument) -> DoclingReferenceMaps:
    return DoclingReferenceMaps(
        page_ids_by_ref={page_ref(page): str(page.page_id) for page in source.pages},
        element_ids_by_ref={
            element_ref(element): str(element.element_id) for element in source.elements
        },
        table_ids_by_ref={table_ref(table): str(table.table_id) for table in source.tables},
    )


def payload_with_resolved_docling_refs(
    payload: dict[str, object],
    *,
    source: ExtractionSourceDocument,
) -> tuple[dict[str, object], dict[str, object]]:
    maps = docling_reference_maps(source)
    resolved = deepcopy(payload)
    resolved_count = _resolve_docling_refs_in_value(resolved, maps=maps)
    if resolved_count == 0:
        return resolved, {}
    return resolved, {
        "stable_docling_refs_resolved": resolved_count,
        "stable_docling_ref_policy": "resolve_prompt_refs_to_persisted_docling_ids",
    }


def _resolve_docling_refs_in_value(
    value: object,
    *,
    maps: DoclingReferenceMaps,
) -> int:
    if isinstance(value, list):
        return sum(_resolve_docling_refs_in_value(item, maps=maps) for item in value)
    if not isinstance(value, dict):
        return 0

    resolved_count = 0
    for key, resolver in (
        ("page_id", maps.resolve_page_id),
        ("pageId", maps.resolve_page_id),
        ("element_id", maps.resolve_element_id),
        ("elementId", maps.resolve_element_id),
        ("table_id", maps.resolve_table_id),
        ("tableId", maps.resolve_table_id),
    ):
        raw_value = value.get(key)
        if not isinstance(raw_value, str):
            continue
        resolved = resolver(raw_value)
        if resolved is None:
            continue
        value[key] = resolved
        resolved_count += 1

    for item in value.values():
        resolved_count += _resolve_docling_refs_in_value(item, maps=maps)
    return resolved_count
