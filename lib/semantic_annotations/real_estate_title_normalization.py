from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from typing import Any
from uuid import UUID

from lib.extraction.models import ExtractionSourceDocument
from lib.semantic_annotations.docling_audit import build_docling_audit
from lib.semantic_annotations.docling_targets import DOCLING_STRUCTURAL_REGION_SOURCE
from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    SemanticGroundingRef,
    SemanticRegionAnnotation,
)

_SELLER_INFO_FIELDS = (
    "seller_name",
    "property_address",
    "file_number",
    "title_company",
    "phone",
    "email",
    "mailing_address",
    "forwarding_address",
    "marital_status",
    "citizenship",
    "closing_attendance",
)
_SELLER_ENTRY_HEADING_TERMS = (
    "seller information",
    "seller 1",
    "seller 2",
)
_SELLER_ENTRY_SECONDARY_HEADING_TERMS = ("seller questionnaire",)
_SELLER_ENTRY_DETAIL_TERMS = (
    "social security",
    "ss#",
    "ss #",
    "ssn",
    "tax id",
    "marital status",
    "current mailing address",
    "email address",
    "forwarding address",
    "future mailing address",
    "mailing address",
    "phone number",
    "state of residency",
)
_SELLER_QUESTION_HEADING_TERMS = (
    "seller questions",
    "important seller questions",
)
_SELLER_QUESTION_DETAIL_TERMS = (
    "attending the closing",
    "bankruptcy",
    "citizenship",
    "driver's license",
    "drivers license",
    "marital status",
    "power of attorney",
    "u.s. citizens",
    "us citizens",
    "vested in title",
)
_COVER_LETTER_TERMS = (
    "dear",
    "forwarding the attached questionnaire",
    "opportunity to be of service",
    "redfin",
    "your key contact person",
)
_MORTGAGE_PAYOFF_TERMS = (
    "account #",
    "lender name",
    "mortgage information",
    "payoff",
    "payoff figures",
    "release information",
    "seller signature",
    "type of loan",
)
_MAX_SELLER_INFO_PAGES = 4


def normalize_real_estate_title_regions(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
    regions: list[SemanticRegionAnnotation],
) -> list[SemanticRegionAnnotation]:
    if not _is_real_estate_title_source(source, manifest):
        return regions

    seller_regions = [
        region for region in regions if region.semantic_type == "seller_information_block"
    ]
    if not seller_regions:
        return regions

    normalized: list[SemanticRegionAnnotation] = [
        region for region in regions if region.semantic_type != "seller_information_block"
    ]
    normalized.extend(
        _seller_info_regions(
            source=source,
            model_regions=seller_regions,
        )
    )
    return normalized


def _is_real_estate_title_source(
    source: ExtractionSourceDocument,
    manifest: DocumentSemanticManifest,
) -> bool:
    document_type = _document_type(manifest)
    source_family = source.family.strip().lower()
    if document_type == "real_estate_title" or source_family == "real_estate_title":
        return True
    return "real_estate_title" in build_docling_audit(source).suggested_family_hints


def _seller_info_regions(
    *,
    source: ExtractionSourceDocument,
    model_regions: list[SemanticRegionAnnotation],
) -> list[SemanticRegionAnnotation]:
    expected_fields = _expected_fields(model_regions)
    page_candidates = _seller_info_page_candidates(source)
    if not page_candidates:
        return _fallback_seller_info_regions(source, model_regions)

    regions: list[SemanticRegionAnnotation] = []
    for index, (page_number, page_id, score) in enumerate(page_candidates[:_MAX_SELLER_INFO_PAGES]):
        regions.append(
            SemanticRegionAnnotation(
                semantic_type="seller_information_block",
                priority="high",
                granite_task="kvp",
                target_schema="document_observation",
                expected_fields=expected_fields,
                grounding=SemanticGroundingRef(kind="page", page_id=page_id),
                review_required=True,
                reason="Docling text anchors indicate a real-estate seller-information page.",
                confidence=min(0.86, 0.68 + (score * 0.04)),
                metadata={
                    "region_source": DOCLING_STRUCTURAL_REGION_SOURCE,
                    "source_signal": "text",
                    "coverage_role": "primary" if index == 0 else "continuation",
                    "extraction_scope": "page",
                    "must_extract_reason": "real_estate_title_seller_information",
                    "docling_anchor_page_number": page_number,
                    "semantic_planner_normalization": {
                        "reason": "real_estate_title_docling_seller_info_page_coverage",
                    },
                },
            )
        )
    return regions


def _expected_fields(model_regions: list[SemanticRegionAnnotation]) -> tuple[str, ...]:
    fields: list[str] = []
    for region in model_regions:
        fields.extend(region.expected_fields)
    fields.extend(_SELLER_INFO_FIELDS)
    return tuple(dict.fromkeys(fields))


def _seller_info_page_candidates(source: ExtractionSourceDocument) -> list[tuple[int, UUID, int]]:
    elements_by_page: defaultdict[int, list[str]] = defaultdict(list)
    for element in source.elements:
        if element.text:
            elements_by_page[element.page_number].append(element.text)

    candidates: list[tuple[int, UUID, int]] = []
    for page in source.pages:
        text = _normalized_text(" ".join([page.text, *elements_by_page.get(page.page_number, [])]))
        score = _seller_information_page_score(text)
        if score <= 0:
            continue
        candidates.append((page.page_number, page.page_id, score))
    return sorted(candidates, key=lambda item: item[0])


def _seller_information_page_score(text: str) -> int:
    compact = _compact_text(text)
    entry_heading_score = _term_score(text, compact, _SELLER_ENTRY_HEADING_TERMS)
    entry_secondary_score = _term_score(text, compact, _SELLER_ENTRY_SECONDARY_HEADING_TERMS)
    entry_detail_score = _term_score(text, compact, _SELLER_ENTRY_DETAIL_TERMS)
    question_heading_score = _term_score(text, compact, _SELLER_QUESTION_HEADING_TERMS)
    question_detail_score = _term_score(text, compact, _SELLER_QUESTION_DETAIL_TERMS)
    cover_letter_score = _term_score(text, compact, _COVER_LETTER_TERMS)
    mortgage_payoff_score = _term_score(text, compact, _MORTGAGE_PAYOFF_TERMS)

    entry_page = (entry_heading_score >= 1 and entry_detail_score >= 2) or (
        entry_secondary_score >= 1 and entry_detail_score >= 3
    )
    question_page = question_heading_score >= 1 and question_detail_score >= 2
    if not entry_page and not question_page:
        return 0

    if cover_letter_score >= 2 and entry_heading_score == 0:
        return 0
    if mortgage_payoff_score >= 2 and not question_page:
        return 0

    return (
        entry_heading_score
        + entry_secondary_score
        + entry_detail_score
        + question_heading_score
        + question_detail_score
    )


def _fallback_seller_info_regions(
    source: ExtractionSourceDocument,
    model_regions: list[SemanticRegionAnnotation],
) -> list[SemanticRegionAnnotation]:
    best_by_page: dict[int, SemanticRegionAnnotation] = {}
    best_without_page: SemanticRegionAnnotation | None = None
    for region in model_regions:
        page_number = _region_page_number(source, region)
        if page_number is None:
            if best_without_page is None or _region_preference_key(region) < _region_preference_key(
                best_without_page
            ):
                best_without_page = region
            continue
        existing = best_by_page.get(page_number)
        if existing is None or _region_preference_key(region) < _region_preference_key(existing):
            best_by_page[page_number] = region

    normalized: list[SemanticRegionAnnotation] = []
    if best_without_page is not None:
        normalized.append(
            replace(
                best_without_page,
                review_required=True,
                metadata={
                    **best_without_page.metadata,
                    "semantic_planner_normalization": {
                        "reason": "real_estate_title_model_seller_info_dedupe",
                    },
                },
            )
        )
    for page_number in sorted(best_by_page):
        region = best_by_page[page_number]
        page_id = _page_id_for_page_number(source, page_number) or region.grounding.page_id
        if page_id is None:
            normalized.append(region)
            continue
        metadata = {
            **region.metadata,
            "semantic_planner_normalization": {
                "reason": "real_estate_title_model_seller_info_page_dedupe",
            },
        }
        normalized.append(
            replace(
                region,
                grounding=SemanticGroundingRef(kind="page", page_id=page_id),
                review_required=True,
                metadata=metadata,
            )
        )
    return normalized[:_MAX_SELLER_INFO_PAGES]


def _region_preference_key(region: SemanticRegionAnnotation) -> tuple[object, ...]:
    priority_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return (
        priority_rank.get(region.priority, 4),
        0 if region.metadata.get("region_source") == DOCLING_STRUCTURAL_REGION_SOURCE else 1,
        -(region.confidence or 0.0),
    )


def _region_page_number(
    source: ExtractionSourceDocument,
    region: SemanticRegionAnnotation,
) -> int | None:
    grounding = region.grounding
    if grounding.page_id is not None:
        return _page_number_for_id(source, grounding.page_id)
    if grounding.table_id is not None:
        return _page_number_for_table(source, grounding.table_id)
    return None


def _page_number_for_id(source: ExtractionSourceDocument, page_id: UUID) -> int | None:
    for page in source.pages:
        if page.page_id == page_id:
            return page.page_number
    return None


def _page_number_for_table(source: ExtractionSourceDocument, table_id: UUID) -> int | None:
    for table in source.tables:
        if table.table_id == table_id:
            return table.page_number
    return None


def _page_id_for_page_number(source: ExtractionSourceDocument, page_number: int) -> UUID | None:
    for page in source.pages:
        if page.page_number == page_number:
            return page.page_id
    return None


def _document_type(manifest: DocumentSemanticManifest) -> str | None:
    value = manifest.manifest.get("document_type")
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _compact_text(value: str) -> str:
    return value.replace(" ", "")


def _term_score(text: str, compact: str, terms: tuple[str, ...]) -> int:
    score = 0
    for term in terms:
        normalized = _normalized_text(term)
        if normalized in text or _compact_text(normalized) in compact:
            score += 1
    return score
