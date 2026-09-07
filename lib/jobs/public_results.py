"""Typed public projection of worker summaries, including historical rows.

The internal result ledger is not an arbitrary JSON response endpoint. Detailed
document content/provenance remains behind its dedicated authorized read models.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from uuid import UUID

_IDS = {
    "document_id",
    "original_asset_id",
    "docling_asset_id",
    "annotation_id",
    "extraction_id",
    "aggregate_extraction_id",
    "queued_extraction_job_id",
    "queued_semantic_annotation_job_id",
}
_ID_LISTS = {"queued_granite_job_ids", "region_extraction_ids", "aggregate_extraction_ids"}
_COUNTS = {
    "page_count",
    "element_count",
    "table_count",
    "chunk_count",
    "candidate_count",
    "canonical_count",
    "review_task_count",
    "source_count",
    "inserted_count",
    "skipped_count",
    "suggestion_count",
    "deadline_count",
    "dimensions",
}
_STATUSES = {
    "ingest_status",
    "parse_status",
    "preview_status",
    "semantic_annotation_status",
    "classification_status",
    "extraction_status",
    "embedding_status",
    "relationship_status",
    "review_status",
}
_STATUS_VALUES = {
    "acknowledged",
    "generated",
    "succeeded",
    "failed",
    "pending",
    "needs_review",
    "accepted",
    "auto_accepted",
    "user_confirmed",
    "user_corrected",
    "rejected",
    "superseded",
    "extracted_cleanly",
    "needs_human_review",
    "insufficient_signal",
    "no_extraction_target",
}
_FAMILIES = {
    "receipt",
    "invoice",
    "medical_eob",
    "bill",
    "statement",
    "insurance",
    "legal",
    "tax",
    "warranty",
    "identity",
    "note",
    "reference",
    "generic",
    "unknown",
}


def public_job_result(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key in _IDS:
        if key in value and (identifier := _uuid(value[key])) is not None:
            result[key] = identifier
    for key in _ID_LISTS:
        entries = value.get(key)
        if isinstance(entries, list) and len(entries) <= 1000:
            parsed = [_uuid(entry) for entry in entries]
            if all(identifier is not None for identifier in parsed):
                result[key] = parsed
    for key in _COUNTS:
        count = value.get(key)
        if _is_count(count):
            result[key] = count
    for key in _STATUSES:
        status = value.get(key)
        if isinstance(status, str) and status in _STATUS_VALUES:
            result[key] = status
    if isinstance(family := value.get("family"), str) and family in _FAMILIES:
        result["family"] = family
    if value.get("orchestration_mode") == "semantic_document":
        result["orchestration_mode"] = "semantic_document"
    digest = value.get("sha256")
    if isinstance(digest, str) and re.fullmatch(r"[a-fA-F0-9]{64}", digest):
        result["sha256"] = digest.lower()
    quality = value.get("phase8_quality")
    if isinstance(quality, Mapping):
        result["phase8_quality"] = {
            key: quality[key]
            for key in {"review_required", "visual_embedding_eligible", "qwen_route_eligible"}
            if type(quality.get(key)) is bool
        }
    counts = value.get("modality_counts")
    if isinstance(counts, Mapping):
        result["modality_counts"] = {
            key: counts[key] for key in {"text", "image", "visual"} if _is_count(counts.get(key))
        }
    return result


def _uuid(value: object) -> str | None:
    if not isinstance(value, str | UUID):
        return None
    try:
        return str(UUID(str(value)))
    except ValueError:
        return None


def _is_count(value: object) -> bool:
    return type(value) is int and 0 <= value <= 2**31 - 1
