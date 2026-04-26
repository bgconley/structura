from __future__ import annotations

from typing import Protocol

from lib.extraction.heuristics import invoice_payload, medical_eob_payload, receipt_payload
from lib.extraction.models import ExtractionSourceDocument, GatewayExtraction, ModelRoute


class ExtractionGateway(Protocol):
    def extract(
        self,
        source: ExtractionSourceDocument,
        *,
        schema_name: str,
        route_profile: str,
    ) -> GatewayExtraction: ...


class DoclingHeuristicGateway:
    """Deterministic Phase 4 gateway backed by canonical Docling text."""

    def extract(
        self,
        source: ExtractionSourceDocument,
        *,
        schema_name: str,
        route_profile: str,
    ) -> GatewayExtraction:
        route = ModelRoute(
            source_engine="docling",
            model_name="docling-heuristic-extractor",
            model_version="phase4-v1",
            prompt_version="no-prompt-deterministic-v1",
            route_profile=route_profile,
        )
        if schema_name == "receipt":
            normalized = receipt_payload(source)
        elif schema_name == "invoice":
            normalized = invoice_payload(source)
        elif schema_name == "medical_eob":
            normalized = medical_eob_payload(source)
        else:
            raise ValueError(f"Unsupported extraction schema: {schema_name}")
        return GatewayExtraction(
            schema_name=schema_name,
            schema_version="v1",
            route=route,
            normalized_json=normalized,
            raw_output_json={
                "source": "docling_canonical_text",
                "schema_name": schema_name,
                "route_profile": route_profile,
                "normalized": normalized,
            },
        )
