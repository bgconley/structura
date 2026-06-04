from __future__ import annotations

from typing import Any

from lib.extraction.evidence_concretizer import evidence_ref_from_context
from lib.extraction.evidence_context import EvidenceContext


def line_item_provenance(
    item: dict[str, Any],
    evidence_context: EvidenceContext | None,
) -> dict[str, Any]:
    provenance: dict[str, Any] = {}
    row_index = optional_int(item.get("row_index"))
    table_id = item.get("table_id") or (
        str(evidence_context.table_id) if evidence_context else None
    )
    page_number = item.get("page_number") or (
        evidence_context.page_number if evidence_context else None
    )
    if row_index is not None:
        provenance["row_index"] = row_index
    if table_id not in (None, ""):
        provenance["table_id"] = str(table_id)
    if page_number not in (None, ""):
        provenance["page_number"] = int(page_number)
    return provenance


def line_item_evidence(
    item: dict[str, Any],
    source_text: object,
    evidence_context: EvidenceContext | None,
) -> dict[str, Any]:
    text = str(source_text or "").strip()
    if evidence_context is not None:
        evidence = evidence_ref_from_context(evidence_context=evidence_context, source_text=text)
    else:
        evidence = {
            "source_engine": "granite_vision_3b",
            "source_text": text,
            "confidence": 0.72,
        }

    evidence.update(line_item_provenance(item, evidence_context))
    return evidence


def optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
