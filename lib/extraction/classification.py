from __future__ import annotations

from datetime import UTC, datetime

from lib.extraction.evidence import EvidenceResolver
from lib.extraction.heuristics import classify_text_signals
from lib.extraction.models import ClassificationDecision, ExtractionSourceDocument
from lib.extraction.schema_registry import ExtractionSchemaRegistry

TARGET_EXTRACTION_SCHEMAS = {"receipt", "invoice", "medical_eob"}


def classify_document(
    source: ExtractionSourceDocument,
    *,
    registry: ExtractionSchemaRegistry | None = None,
) -> ClassificationDecision:
    family, subtype, reasons, confidence = classify_text_signals(source)
    route_profile = (
        "docling_plus_structured_extraction"
        if family in TARGET_EXTRACTION_SCHEMAS
        else "docling_only"
    )
    needs_review = confidence < 0.7 or family == "medical_eob"
    evidence = EvidenceResolver(source).first_page_evidence(source_engine="system")
    payload = {
        "schema_name": "document_classification",
        "schema_version": "v1",
        "document_id": str(source.document_id),
        "family": family,
        "route_profile": route_profile,
        "reasons": reasons,
        "confidence": {"overall": confidence, "schema_fit": confidence},
        "evidence": evidence,
        "created_at": datetime.now(UTC).isoformat(),
        "model_trace": {
            "source_engine": "system",
            "model_name": "phase4-heuristic-classifier",
            "model_version": "v1",
            "signals": reasons,
            "needs_review": needs_review,
        },
    }
    if subtype:
        payload["subtype"] = subtype
    (registry or ExtractionSchemaRegistry()).validate("document_classification", payload)
    return ClassificationDecision(payload=payload, needs_review=needs_review)
