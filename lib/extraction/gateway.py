from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

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
        qwen_review_route = route_profile == "qwen_primary_review_required"
        route = ModelRoute(
            source_engine="docling",
            model_name=(
                "docling-heuristic-handwriting-review-route"
                if qwen_review_route
                else "docling-heuristic-extractor"
            ),
            model_version="phase8-v1" if qwen_review_route else "phase4-v1",
            prompt_version=(
                "docling-handwriting-review-required-v1"
                if qwen_review_route
                else "no-prompt-deterministic-v1"
            ),
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
        if qwen_review_route:
            normalized = _mark_qwen_review_required(normalized)
        return GatewayExtraction(
            schema_name=schema_name,
            schema_version="v1",
            route=route,
            normalized_json=normalized,
            raw_output_json={
                "source": "docling_canonical_text",
                "schema_name": schema_name,
                "route_profile": route_profile,
                "qwen_route_requested": qwen_review_route,
                "qwen_model_invoked": False,
                "normalized": normalized,
            },
        )


def _mark_qwen_review_required(payload: dict[str, object]) -> dict[str, object]:
    normalized = dict(payload)
    confidence = _mapping_as_dict(normalized.get("confidence"))
    confidence["overall"] = min(float(confidence.get("overall") or 0.0), 0.68)
    confidence["schema_fit"] = min(float(confidence.get("schema_fit") or 0.0), 0.66)
    normalized["confidence"] = confidence
    validation = _mapping_as_dict(normalized.get("validation"))
    validation["needs_review"] = True
    checks = list(validation.get("checks") or [])
    checks.append(
        {
            "check": "phase8_handwriting_route",
            "status": "needs_review",
            "message": (
                "Qwen-eligible handwriting/degraded-document fallback defaults to human review."
            ),
        }
    )
    normalized["validation"] = {**validation, "checks": checks}
    metadata = _mapping_as_dict(normalized.get("metadata"))
    normalized["metadata"] = {
        **metadata,
        "phase8Route": "qwen_primary_review_required",
        "reviewRequired": True,
    }
    return normalized


def _mapping_as_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
