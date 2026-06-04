from __future__ import annotations

from uuid import uuid4

from lib.extraction.evidence import has_concrete_evidence
from lib.extraction.evidence_context import EvidenceContext
from lib.extraction.model_output_observations import (
    looks_like_schema_echo,
    observations_from_model_payload,
)


def test_model_output_observations_filter_schema_and_prompt_echoes() -> None:
    document_id = uuid4()
    region_id = uuid4()
    page_id = uuid4()

    assert looks_like_schema_echo({"$schema": "https://json-schema.org/draft/2020-12/schema"})

    observations = observations_from_model_payload(
        {
            "fields": [
                {
                    "name": "seller_name",
                    "value": "Jane Seller",
                    "confidence": "0.74",
                    "source_text": "Seller: Jane Seller",
                },
                {
                    "name": "instructions",
                    "value": "Return only JSON matching this schema",
                },
                {"name": "empty", "value": ""},
            ]
        },
        "granite_generic_kvp.v1",
        evidence_context=EvidenceContext(
            source_engine="granite_vision_3b",
            document_id=document_id,
            semantic_region_id=region_id,
            page_id=page_id,
            page_number=2,
        ),
    )

    assert len(observations) == 1
    assert observations[0]["field_name"] == "seller_name"
    assert observations[0]["value_type"] == "string"
    assert observations[0]["confidence"] == 0.74
    assert has_concrete_evidence(observations[0]["evidence"]) is True
