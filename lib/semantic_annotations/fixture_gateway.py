from __future__ import annotations

from lib.extraction.heuristics import classify_text_signals
from lib.extraction.models import ExtractionSourceDocument
from lib.semantic_annotations.models import (
    DocumentSemanticManifest,
    PageSemanticAnnotation,
    SemanticAnnotationResult,
    SemanticGroundingRef,
    SemanticRegionAnnotation,
)

FIXTURE_SEMANTIC_PROFILE = "structura-fixture-semantic-annotator:v1"


class FixtureSemanticAnnotationGateway:
    def annotate(
        self,
        source: ExtractionSourceDocument,
        *,
        quality_mode: str,
    ) -> SemanticAnnotationResult:
        page = source.pages[0]
        fixture_family = _fixture_family(source)
        semantic_type = _default_semantic_type(fixture_family)
        region = SemanticRegionAnnotation(
            semantic_type=semantic_type,
            priority="high",
            granite_task="kvp",
            target_schema=fixture_family if fixture_family != "generic" else None,
            expected_fields=(),
            grounding=SemanticGroundingRef(kind="page", page_id=page.page_id),
            reason="Deterministic fixture annotation for local tests.",
            confidence=0.8,
            review_required=quality_mode != "smart",
        )
        manifest = DocumentSemanticManifest(
            document_id=source.document_id,
            household_id=source.household_id,
            quality_mode=quality_mode,  # type: ignore[arg-type]
            profile_name=FIXTURE_SEMANTIC_PROFILE,
            source_engine="system",
            model_name="structura-fixture-semantic-annotator",
            model_version="v1",
            prompt_version=f"phase8_5-semantic-{quality_mode}-fixture-v1",
            pages=[
                PageSemanticAnnotation(
                    page_id=page.page_id,
                    page_number=page.page_number,
                    page_role="document_summary",
                    document_type_hint=fixture_family,
                    extraction_usefulness="medium",
                    has_structured_targets=fixture_family != "generic",
                    confidence=0.8,
                )
            ],
            regions=[region],
            confidence={"overall": 0.8},
            manifest={"document_type": fixture_family, "fixture": True},
            review_required=quality_mode != "smart",
            input_page_hashes=tuple(
                page.image_sha256 for page in source.pages if page.image_sha256
            ),
        )
        return SemanticAnnotationResult(manifest=manifest)


def _fixture_family(source: ExtractionSourceDocument) -> str:
    if source.family != "generic":
        return source.family
    family, _subtype, _reasons, confidence = classify_text_signals(source)
    if family != "generic" and confidence >= 0.7:
        return family
    return source.family


def _default_semantic_type(family: str) -> str:
    if family == "medical_eob":
        return "patient_responsibility_summary"
    if family == "receipt":
        return "receipt_line_item_table"
    if family == "invoice":
        return "billing_summary"
    return "unknown"
