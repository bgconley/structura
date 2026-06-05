from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

QualityMode = Literal["smart"]
AnnotationStatus = Literal["pending", "succeeded", "failed", "superseded"]
Priority = Literal["low", "medium", "high", "critical"]
GroundingKind = Literal["page", "element", "table", "unmatched_region"]


@dataclass(frozen=True)
class SemanticGroundingRef:
    kind: GroundingKind
    page_id: UUID | None = None
    element_id: UUID | None = None
    table_id: UUID | None = None


@dataclass(frozen=True)
class PageSemanticAnnotation:
    page_id: UUID
    page_number: int
    page_role: str
    document_type_hint: str | None = None
    extraction_usefulness: str = "unknown"
    is_boilerplate: bool = False
    has_structured_targets: bool = False
    ambiguous: bool = False
    escalation_required: bool = False
    reason: str | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticRegionAnnotation:
    semantic_type: str
    priority: Priority
    granite_task: str | None
    grounding: SemanticGroundingRef
    target_schema: str | None = None
    expected_fields: tuple[str, ...] = ()
    review_required: bool = False
    reason: str | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticExtractionTask:
    region_id: UUID
    annotation_id: UUID
    document_id: UUID
    semantic_type: str
    granite_task: str
    target_schema: str | None
    expected_fields: tuple[str, ...]
    grounding: SemanticGroundingRef
    reason: str | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentSemanticManifest:
    document_id: UUID
    household_id: UUID
    quality_mode: QualityMode
    profile_name: str
    source_engine: str
    model_name: str
    model_version: str
    prompt_version: str
    pages: list[PageSemanticAnnotation]
    regions: list[SemanticRegionAnnotation]
    confidence: dict[str, Any]
    manifest: dict[str, Any]
    review_required: bool = False
    escalation_reason: str | None = None
    input_page_hashes: tuple[str, ...] = ()
    docling_parse_asset_id: UUID | None = None
    docling_parse_sha256: str | None = None


@dataclass(frozen=True)
class SemanticAnnotationResult:
    manifest: DocumentSemanticManifest
    status: AnnotationStatus = "succeeded"
