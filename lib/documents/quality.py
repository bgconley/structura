from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from lib.db.connection import db_connection
from lib.review.task_repository import upsert_review_task

LOW_TEXT_CHAR_THRESHOLD = 32
LOW_OCR_CONFIDENCE_THRESHOLD = 0.62
COMPLEX_LAYOUT_TABLE_THRESHOLD = 2
COMPLEX_LAYOUT_FIGURE_THRESHOLD = 2


@dataclass(frozen=True)
class PageQualityInput:
    page_number: int
    text: str
    has_text_layer: bool | None
    ocr_confidence: float | None
    metadata: Mapping[str, Any]
    table_count: int = 0
    figure_count: int = 0


@dataclass(frozen=True)
class PageQualitySignals:
    page_number: int
    reasons: tuple[str, ...]
    review_required: bool
    visual_embedding_eligible: bool
    qwen_route_eligible: bool
    has_handwriting: bool
    has_text_layer: bool | None
    ocr_confidence: float | None
    text_density: int

    def as_json(self) -> dict[str, Any]:
        return {
            "pageNumber": self.page_number,
            "reasons": list(self.reasons),
            "reviewRequired": self.review_required,
            "visualEmbeddingEligible": self.visual_embedding_eligible,
            "qwenRouteEligible": self.qwen_route_eligible,
            "hasHandwriting": self.has_handwriting,
            "hasTextLayer": self.has_text_layer,
            "ocrConfidence": self.ocr_confidence,
            "textDensity": self.text_density,
            "summary": quality_summary_text(self.reasons),
        }


@dataclass(frozen=True)
class DocumentQualitySummary:
    reasons: tuple[str, ...]
    review_required: bool
    visual_embedding_eligible: bool
    qwen_route_eligible: bool
    has_handwriting: bool
    difficult_page_numbers: tuple[int, ...]
    pages: tuple[PageQualitySignals, ...]

    def as_json(self) -> dict[str, Any]:
        return {
            "reasons": list(self.reasons),
            "reviewRequired": self.review_required,
            "visualEmbeddingEligible": self.visual_embedding_eligible,
            "qwenRouteEligible": self.qwen_route_eligible,
            "hasHandwriting": self.has_handwriting,
            "difficultPageNumbers": list(self.difficult_page_numbers),
            "summary": quality_summary_text(self.reasons),
            "pages": [page.as_json() for page in self.pages],
        }


def classify_page_quality(page: PageQualityInput) -> PageQualitySignals:
    reasons: list[str] = []
    text_density = len((page.text or "").strip())
    text_casefold = (page.text or "").casefold()
    has_handwriting = (
        _metadata_bool(
            page.metadata,
            ("hasHandwriting", "has_handwriting"),
        )
        or "handwriting" in text_casefold
        or "handwritten" in text_casefold
    )
    degraded = _metadata_value(page.metadata, ("visualQuality", "visual_quality")) in {
        "degraded",
        "low_quality",
        "scan_degraded",
    } or _metadata_bool(page.metadata, ("degradedScan", "degraded_scan"))
    parse_warnings = _metadata_sequence(page.metadata, ("parseWarnings", "parse_warnings"))

    if has_handwriting:
        reasons.append("handwriting")
    if page.has_text_layer is False:
        reasons.append("missing_text_layer")
    if text_density < LOW_TEXT_CHAR_THRESHOLD:
        reasons.append("low_text_density")
    if page.ocr_confidence is not None and page.ocr_confidence < LOW_OCR_CONFIDENCE_THRESHOLD:
        reasons.append("low_ocr_confidence")
    if degraded:
        reasons.append("degraded_scan")
    if (
        page.table_count >= COMPLEX_LAYOUT_TABLE_THRESHOLD
        or page.figure_count >= COMPLEX_LAYOUT_FIGURE_THRESHOLD
        or _metadata_bool(page.metadata, ("complexLayout", "complex_layout"))
    ):
        reasons.append("complex_layout")
    if parse_warnings:
        reasons.append("parse_warnings")
    if not reasons:
        reasons.append("digital_text_page")

    difficult = reasons != ["digital_text_page"]
    qwen_route_eligible = any(
        reason in set(reasons)
        for reason in (
            "handwriting",
            "missing_text_layer",
            "low_ocr_confidence",
            "degraded_scan",
            "complex_layout",
        )
    )
    return PageQualitySignals(
        page_number=page.page_number,
        reasons=tuple(dict.fromkeys(reasons)),
        review_required=any(
            reason in set(reasons)
            for reason in (
                "handwriting",
                "missing_text_layer",
                "low_ocr_confidence",
                "degraded_scan",
                "parse_warnings",
            )
        ),
        visual_embedding_eligible=difficult,
        qwen_route_eligible=qwen_route_eligible,
        has_handwriting=has_handwriting,
        has_text_layer=page.has_text_layer,
        ocr_confidence=page.ocr_confidence,
        text_density=text_density,
    )


def summarize_document_quality(pages: Sequence[PageQualityInput]) -> DocumentQualitySummary:
    page_signals = tuple(classify_page_quality(page) for page in pages)
    reasons = tuple(
        dict.fromkeys(reason for page in page_signals for reason in page.reasons).keys()
    )
    difficult_pages = tuple(
        page.page_number
        for page in page_signals
        if page.review_required or page.visual_embedding_eligible
    )
    return DocumentQualitySummary(
        reasons=reasons,
        review_required=any(page.review_required for page in page_signals),
        visual_embedding_eligible=any(page.visual_embedding_eligible for page in page_signals),
        qwen_route_eligible=any(page.qwen_route_eligible for page in page_signals),
        has_handwriting=any(page.has_handwriting for page in page_signals),
        difficult_page_numbers=difficult_pages,
        pages=page_signals,
    )


def evaluate_document_quality(document_id: UUID) -> DocumentQualitySummary:
    with db_connection() as conn:
        with conn.cursor() as cur:
            pages = _load_quality_inputs(cur, document_id)
            summary = summarize_document_quality(pages)
            _persist_quality_summary(cur, document_id, summary)
            if summary.review_required:
                _upsert_document_quality_review_task(cur, document_id, summary)
        conn.commit()
    return summary


def quality_summary_from_metadata(metadata: object) -> dict[str, Any] | None:
    if not isinstance(metadata, Mapping):
        return None
    phase8 = metadata.get("phase8")
    if not isinstance(phase8, Mapping):
        return None
    quality = phase8.get("quality")
    return dict(quality) if isinstance(quality, Mapping) else None


def quality_summary_text(reasons: Sequence[str]) -> str:
    labels = {
        "handwriting": "handwriting detected",
        "missing_text_layer": "missing text layer",
        "low_text_density": "sparse text",
        "low_ocr_confidence": "low OCR confidence",
        "degraded_scan": "degraded scan",
        "complex_layout": "complex layout",
        "parse_warnings": "parse warnings",
        "digital_text_page": "digital text page",
    }
    return ", ".join(labels.get(reason, reason.replace("_", " ")) for reason in reasons)


def _load_quality_inputs(cur: Any, document_id: UUID) -> list[PageQualityInput]:
    cur.execute(
        """
        SELECT
          p.id,
          p.page_number,
          p.text_content,
          p.has_text_layer,
          p.ocr_confidence,
          p.metadata_json,
          (
            SELECT count(*)
            FROM document_tables t
            WHERE t.page_id = p.id
          ) AS table_count,
          (
            SELECT count(*)
            FROM document_elements e
            WHERE e.page_id = p.id
              AND e.element_type IN ('figure', 'form_field', 'signature')
          ) AS figure_count
        FROM document_pages p
        WHERE p.document_id = %s
        ORDER BY p.page_number
        """,
        (document_id,),
    )
    rows = cur.fetchall()
    return [
        PageQualityInput(
            page_number=int(row["page_number"]),
            text=str(row["text_content"] or ""),
            has_text_layer=row["has_text_layer"],
            ocr_confidence=(
                float(row["ocr_confidence"]) if row["ocr_confidence"] is not None else None
            ),
            metadata=dict(row["metadata_json"] or {}),
            table_count=int(row["table_count"] or 0),
            figure_count=int(row["figure_count"] or 0),
        )
        for row in rows
    ]


def _persist_quality_summary(
    cur: Any,
    document_id: UUID,
    summary: DocumentQualitySummary,
) -> None:
    page_by_number = {page.page_number: page for page in summary.pages}
    for page_number, page in page_by_number.items():
        cur.execute(
            """
            UPDATE document_pages
            SET metadata_json = jsonb_set(
                  COALESCE(metadata_json, '{}'::jsonb),
                  '{phase8,quality}',
                  %s::jsonb,
                  true
                ),
                updated_at = now()
            WHERE document_id = %s
              AND page_number = %s
            """,
            (Jsonb(page.as_json()), document_id, page_number),
        )
    cur.execute(
        """
        UPDATE documents
        SET has_handwriting = %s,
            review_status = CASE
              WHEN %s AND review_status IN ('unreviewed', 'auto_accepted') THEN 'needs_review'
              ELSE review_status
            END,
            metadata_json = jsonb_set(
              COALESCE(metadata_json, '{}'::jsonb),
              '{phase8,quality}',
              %s::jsonb,
              true
            ),
            updated_at = now()
        WHERE id = %s
          AND deleted_at IS NULL
        """,
        (
            summary.has_handwriting,
            summary.review_required,
            Jsonb(summary.as_json()),
            document_id,
        ),
    )


def _upsert_document_quality_review_task(
    cur: Any,
    document_id: UUID,
    summary: DocumentQualitySummary,
) -> None:
    first_page = summary.difficult_page_numbers[0] if summary.difficult_page_numbers else None
    upsert_review_task(
        cur,
        document_id=document_id,
        extraction_id=None,
        task_type="document_quality",
        reason=f"Difficult document requires review: {quality_summary_text(summary.reasons)}.",
        priority=88 if summary.has_handwriting else 72,
        metadata={
            "pageNumber": first_page,
            "reasons": list(summary.reasons),
            "visualEmbeddingEligible": summary.visual_embedding_eligible,
            "qwenRouteEligible": summary.qwen_route_eligible,
            "phase": "phase8",
        },
    )


def _metadata_bool(metadata: Mapping[str, Any], keys: Sequence[str]) -> bool:
    return any(bool(_metadata_value(metadata, (key,))) for key in keys)


def _metadata_value(metadata: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in metadata:
            return metadata[key]
    return None


def _metadata_sequence(metadata: Mapping[str, Any], keys: Sequence[str]) -> list[Any]:
    value = _metadata_value(metadata, keys)
    return value if isinstance(value, list) else []
