from __future__ import annotations

from uuid import uuid4

from lib.extraction.evidence import has_concrete_evidence
from lib.extraction.evidence_context import EvidenceContext
from lib.extraction.model_output_healthcare import healthcare_coverage_decision_output


def test_healthcare_coverage_decision_output_maps_contacts_to_grounded_observations() -> None:
    document_id = uuid4()
    normalized, metadata = healthcare_coverage_decision_output(
        document_id=document_id,
        payload={
            "facts": [
                {
                    "name": "denial_reason",
                    "value": "Not medically necessary",
                    "confidence": 0.86,
                    "source_text": "not medically necessary",
                }
            ],
            "contacts": [
                {
                    "contact_type": "appeal",
                    "phone": "555-0100",
                    "source_text": "Appeals: 555-0100",
                    "confidence": 0.8,
                }
            ],
            "service_lines": [],
            "warnings": [],
        },
        evidence_context=EvidenceContext(
            source_engine="granite_vision_3b",
            document_id=document_id,
            semantic_region_id=uuid4(),
            page_number=1,
        ),
    )

    assert metadata["mapper"] == "granite_healthcare_coverage_decision.v1"
    assert normalized["schema_name"] == "document_observation"
    assert [(item["field_name"], item["value"]) for item in normalized["observations"]] == [
        ("denial_reason", "Not medically necessary"),
        ("contact_1.contact_type", "appeal"),
        ("contact_1.phone", "555-0100"),
    ]
    assert all(has_concrete_evidence(item["evidence"]) for item in normalized["observations"])
