from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from lib.extraction.claims import claims_from_region_envelope
from lib.extraction.observation_reconciliation import (
    reconcile_document_observation_region_extractions,
)
from lib.extraction.reconciliation import RegionExtraction
from lib.extraction.region_envelope import EvidenceRef, RegionExtractionEnvelope, RegionFact


def test_document_observation_region_reconciliation_uses_anchored_claims() -> None:
    document_id = uuid4()
    region_id = uuid4()
    extraction_id = uuid4()
    evidence = EvidenceRef(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        page_number=2,
        element_id="el-2",
        source_engine="granite_vision_3b",
    )
    envelope = RegionExtractionEnvelope(
        document_id=str(document_id),
        semantic_region_id=str(region_id),
        resolved_document_type="real_estate_title",
        semantic_type="generic_form_kvp",
        target_schema="document_observation",
        model_output_schema_name="granite_generic_kvp.v1",
        observations=[
            RegionFact(
                name="real_estate_title.property.address",
                value="123 Main St",
                value_type="string",
                confidence=0.82,
                evidence=[evidence],
            )
        ],
    )

    aggregate = reconcile_document_observation_region_extractions(
        document_id=document_id,
        created_at=datetime.now(UTC),
        regions=[
            RegionExtraction(
                extraction_id=extraction_id,
                semantic_region_id=region_id,
                semantic_type="generic_form_kvp",
                region_envelope=envelope,
                claims=claims_from_region_envelope(envelope),
            )
        ],
    )

    assert aggregate is not None
    assert aggregate["schema_name"] == "document_observation"
    assert aggregate["observations"] == [
        {
            "family": "real_estate_title",
            "field_name": "property.address",
            "value": "123 Main St",
            "value_type": "string",
            "source_text": "123 Main St",
            "confidence": 0.82,
            "evidence": [
                {
                    "document_id": str(document_id),
                    "semantic_region_id": str(region_id),
                    "page_number": 2,
                    "element_id": "el-2",
                    "source_engine": "granite_vision_3b",
                }
            ],
        }
    ]
    assert aggregate["validation"]["needs_review"] is True
    assert aggregate["metadata"]["region_extractions"] == [
        {
            "extraction_id": str(extraction_id),
            "semantic_region_id": str(region_id),
            "semantic_type": "generic_form_kvp",
        }
    ]
    assert aggregate["metadata"]["source_families"] == ["real_estate_title"]
    assert aggregate["metadata"]["claim_resolution_decisions"][0]["decision"] == "accepted"
    assert aggregate["metadata"]["quality_outcome"] == "needs_human_review"


def test_document_observation_region_reconciliation_requires_claims() -> None:
    aggregate = reconcile_document_observation_region_extractions(
        document_id=uuid4(),
        created_at=datetime.now(UTC),
        regions=[
            RegionExtraction(
                extraction_id=uuid4(),
                semantic_region_id=uuid4(),
                semantic_type="generic_form_kvp",
            )
        ],
    )

    assert aggregate is None
