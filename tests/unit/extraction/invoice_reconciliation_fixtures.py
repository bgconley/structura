from __future__ import annotations

from uuid import UUID

from lib.extraction.claims import claims_from_region_envelope
from lib.extraction.reconciliation import RegionExtraction
from lib.extraction.region_envelope import (
    EvidenceRef,
    RegionExtractionEnvelope,
    RegionFact,
    RegionLineItem,
)


def invoice_region(
    *,
    document_id: UUID,
    extraction_id: UUID,
    semantic_region_id: UUID,
    semantic_type: str,
    facts: list[RegionFact] | None = None,
    line_items: list[RegionLineItem] | None = None,
    coverage: dict[str, object] | None = None,
    target_schema: str = "invoice",
    resolved_document_type: str = "invoice",
) -> RegionExtraction:
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(semantic_region_id),
        resolved_document_type=resolved_document_type,
        semantic_type=semantic_type,
        target_schema=target_schema,
        model_output_schema_name="granite_invoice_line_items.v1",
        coverage=coverage or {"schema_name": target_schema},
        facts=facts or [],
        line_items=line_items or [],
    )
    return RegionExtraction(
        extraction_id=extraction_id,
        semantic_region_id=semantic_region_id,
        semantic_type=semantic_type,
        region_envelope=envelope,
        claims=claims_from_region_envelope(envelope),
    )


def evidence(
    document_id: UUID,
    semantic_region_id: UUID,
    *,
    row_index: int,
    table_id: str = "table-1",
) -> EvidenceRef:
    return EvidenceRef(
        document_id=str(document_id),
        semantic_region_id=str(semantic_region_id),
        page_number=1,
        table_id=table_id,
        row_index=row_index,
        source_engine="granite_vision_3b",
    )
