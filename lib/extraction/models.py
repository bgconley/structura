from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

Evidence = dict[str, Any]


@dataclass(frozen=True)
class ParsedPageText:
    page_id: UUID
    page_number: int
    text: str
    image_asset_uri: str | None = None
    image_bytes: bytes | None = None
    image_mime_type: str | None = None
    image_sha256: str | None = None


@dataclass(frozen=True)
class ParsedElementText:
    element_id: UUID
    page_number: int
    ordinal: int
    text: str
    bbox: Any | None = None


@dataclass(frozen=True)
class ParsedTableText:
    table_id: UUID
    page_number: int
    table_index: int
    table_markdown: str | None = None
    table_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractionSourceDocument:
    document_id: UUID
    household_id: UUID
    title: str
    original_filename: str | None
    mime_type: str | None
    family: str
    subtype: str | None
    sensitivity: str
    document_date: date | None
    counterparty_display: str | None
    primary_folder_id: UUID | None
    metadata: dict[str, Any]
    pages: list[ParsedPageText]
    elements: list[ParsedElementText]
    tables: list[ParsedTableText]

    @property
    def full_text(self) -> str:
        return "\n".join(page.text for page in self.pages if page.text)


@dataclass(frozen=True)
class ClassificationDecision:
    payload: dict[str, Any]
    needs_review: bool

    @property
    def family(self) -> str:
        return str(self.payload["family"])

    @property
    def route_profile(self) -> str:
        return str(self.payload["route_profile"])

    @property
    def confidence(self) -> float:
        confidence = self.payload.get("confidence") or {}
        return float(confidence.get("overall") or 0.0)


@dataclass(frozen=True)
class ValidationReport:
    needs_review: bool
    checks: list[dict[str, Any]]

    def as_json(self) -> dict[str, Any]:
        return {"needs_review": self.needs_review, "checks": self.checks}


@dataclass(frozen=True)
class ModelRoute:
    source_engine: str
    model_name: str
    model_version: str
    prompt_version: str
    route_profile: str


@dataclass(frozen=True)
class GatewayExtraction:
    schema_name: str
    schema_version: str
    route: ModelRoute
    normalized_json: dict[str, Any]
    raw_output_json: dict[str, Any]
    model_output_schema_name: str | None = None
    model_output_schema_version: str | None = None
    normalization_json: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractionRunScope:
    extraction_scope: str = "document"
    semantic_annotation_id: UUID | None = None
    source_semantic_region_id: UUID | None = None
    semantic_type: str | None = None
    granite_task: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def document(cls) -> ExtractionRunScope:
        return cls(extraction_scope="document")

    @classmethod
    def aggregate(cls, *, semantic_annotation_id: UUID | None = None) -> ExtractionRunScope:
        return cls(
            extraction_scope="aggregate",
            semantic_annotation_id=semantic_annotation_id,
        )

    @classmethod
    def semantic_region(
        cls,
        *,
        semantic_annotation_id: UUID,
        source_semantic_region_id: UUID,
        semantic_type: str,
        granite_task: str | None,
    ) -> ExtractionRunScope:
        return cls(
            extraction_scope="semantic_region",
            semantic_annotation_id=semantic_annotation_id,
            source_semantic_region_id=source_semantic_region_id,
            semantic_type=semantic_type,
            granite_task=granite_task,
        )


@dataclass(frozen=True)
class CandidateFact:
    field_path: str
    value_type: str
    value: Any
    evidence: list[Evidence]
    ordinal: int = 1
    currency: str | None = None
    confidence: float | None = None
    authority_weight: float = 0.0
    validation: dict[str, Any] = field(default_factory=dict)
    status: str = "proposed"


@dataclass(frozen=True)
class LineItemCandidateFact:
    line_item_type: str
    ordinal: int
    description: str
    evidence: list[Evidence]
    candidate_group: str | None = None
    code: str | None = None
    code_system: str | None = None
    service_date: date | None = None
    quantity: float | None = None
    unit: str | None = None
    unit_price: float | None = None
    gross_amount: float | None = None
    discount_amount: float | None = None
    tax_amount: float | None = None
    net_amount: float | None = None
    currency: str | None = None
    category_hint: str | None = None
    confidence: float | None = None
    authority_weight: float = 0.0
    validation: dict[str, Any] = field(default_factory=dict)
    status: str = "proposed"


@dataclass(frozen=True)
class ObservationCandidateFact:
    observation_family: str | None
    field_name: str
    value_type: str
    value: Any
    evidence: list[Evidence]
    confidence: float | None = None
    validation: dict[str, Any] = field(default_factory=dict)
    status: str = "needs_review"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PersistedExtraction:
    extraction_id: UUID
    review_status: str
    candidate_count: int
    canonical_count: int
    review_task_count: int
