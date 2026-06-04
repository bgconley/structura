from __future__ import annotations

from collections.abc import Mapping

from lib.extraction.models import ExtractionSourceDocument, ParsedPageText
from lib.semantic_annotations.qwen_output_types import ValidatedModelOutputPayload


def canonical_payload_filtered_to_source(
    payload: dict[str, object],
    *,
    source: ExtractionSourceDocument,
) -> ValidatedModelOutputPayload:
    pages = payload.get("pages")
    regions = payload.get("regions")
    if not isinstance(pages, list) or not isinstance(regions, list):
        return ValidatedModelOutputPayload(payload=payload, normalization={})

    valid_page_ids = {str(page.page_id) for page in source.pages}
    source_page_by_id = {str(page.page_id): page for page in source.pages}

    kept_pages: list[object] = []
    dropped_page_ids: list[str] = []
    for page in pages:
        if not isinstance(page, dict):
            kept_pages.append(page)
            continue
        page_id = str(page.get("page_id") or "")
        if page_id in valid_page_ids:
            kept_pages.append(page)
        elif page_id:
            dropped_page_ids.append(page_id)
    missing_blank_pages = _missing_blank_pages(kept_pages, kept_regions=regions, source=source)
    kept_pages.extend(_blank_page_annotation(page) for page in missing_blank_pages)

    kept_regions: list[object] = []
    dropped_region_count = 0
    for region in regions:
        if not isinstance(region, dict):
            kept_regions.append(region)
            continue
        if _region_grounding_is_within_source_window(
            region,
            valid_page_ids=valid_page_ids,
        ):
            kept_regions.append(region)
        else:
            dropped_region_count += 1

    if not dropped_page_ids and not dropped_region_count and not missing_blank_pages:
        return ValidatedModelOutputPayload(payload=payload, normalization={})

    normalized_payload = dict(payload)
    normalized_payload["pages"] = _pages_in_source_order(kept_pages, source_page_by_id)
    normalized_payload["regions"] = kept_regions
    normalization: dict[str, object] = {
        "output_scope_filter_policy": "filter_to_requested_docling_pages",
    }
    if dropped_page_ids:
        normalization["out_of_window_pages_dropped"] = len(dropped_page_ids)
        normalization["out_of_window_page_ids"] = dropped_page_ids[:12]
    if dropped_region_count:
        normalization["out_of_window_regions_dropped"] = dropped_region_count
    if missing_blank_pages:
        normalization["missing_blank_focus_pages_filled"] = len(missing_blank_pages)
        normalization["missing_blank_focus_page_ids"] = [
            str(page.page_id) for page in missing_blank_pages[:12]
        ]
        normalization["missing_blank_focus_page_policy"] = "fill_no_extraction_target_page_only"
    return ValidatedModelOutputPayload(payload=normalized_payload, normalization=normalization)


def _missing_blank_pages(
    pages: list[object],
    *,
    kept_regions: list[object],
    source: ExtractionSourceDocument,
) -> list[ParsedPageText]:
    present_page_ids = {
        str(page.get("page_id") or "")
        for page in pages
        if isinstance(page, dict) and page.get("page_id")
    }
    pages_with_regions = _page_ids_with_regions(kept_regions)
    return [
        page
        for page in source.pages
        if str(page.page_id) not in present_page_ids
        and str(page.page_id) not in pages_with_regions
        and _is_blank_docling_page(page, source=source)
    ]


def _page_ids_with_regions(regions: list[object]) -> set[str]:
    page_ids: set[str] = set()
    for region in regions:
        if not isinstance(region, dict):
            continue
        grounding = region.get("grounding")
        if not isinstance(grounding, dict):
            continue
        page_id = str(grounding.get("page_id") or "")
        if page_id:
            page_ids.add(page_id)
    return page_ids


def _is_blank_docling_page(
    page: ParsedPageText,
    *,
    source: ExtractionSourceDocument,
) -> bool:
    page_number = page.page_number
    if page.text.strip():
        return False
    has_elements = any(element.page_number == page_number for element in source.elements)
    has_tables = any(table.page_number == page_number for table in source.tables)
    return not has_elements and not has_tables


def _blank_page_annotation(page: ParsedPageText) -> dict[str, object]:
    return {
        "page_id": str(page.page_id),
        "page_number": page.page_number,
        "page_role": "unknown",
        "document_type_hint": "no_extraction_target",
        "extraction_usefulness": "none",
        "is_boilerplate": True,
        "has_structured_targets": False,
        "ambiguous": False,
        "escalation_required": False,
        "escalation_reasons": [],
        "reason": "Docling reported a blank/no-signal focus page omitted by the model.",
        "confidence": 1.0,
        "docling_table_signal": "none",
        "requires_cross_page_context": False,
        "material_region_count_hint": 0,
    }


def _pages_in_source_order(
    pages: list[object],
    source_page_by_id: Mapping[str, ParsedPageText],
) -> list[object]:
    source_order = {page_id: index for index, page_id in enumerate(source_page_by_id.keys())}
    return sorted(
        pages,
        key=lambda page: source_order.get(str(page.get("page_id") or ""), len(source_order))
        if isinstance(page, dict)
        else len(source_order),
    )


def _region_grounding_is_within_source_window(
    region: dict[str, object],
    *,
    valid_page_ids: set[str],
) -> bool:
    grounding = region.get("grounding")
    if not isinstance(grounding, dict):
        return True

    page_id = str(grounding.get("page_id") or "")
    if page_id and page_id not in valid_page_ids:
        return False
    return True
