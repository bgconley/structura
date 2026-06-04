from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from lib.model_runtime.contracts import ModelImageInput

VisualInputMode = Literal["full_page", "shadow_full_page", "planned"]
VisualInputScope = Literal[
    "full_page",
    "element_crop",
    "table_crop",
    "bbox_crop",
    "expanded_crop",
    "full_page_retry",
]
BBoxBasis = Literal["pdf_points", "image_pixels", "normalized_1000", "unknown"]
RotationPolicy = Literal["upright", "rotate_90", "rotate_180", "rotate_270", "unknown"]

MAX_CROP_AREA_RATIO = 0.70
MIN_CROP_SHORT_EDGE = 384


@dataclass(frozen=True)
class PixelBBox:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return max(0, self.x1 - self.x0)

    @property
    def height(self) -> int:
        return max(0, self.y1 - self.y0)

    def as_list(self) -> list[int]:
        return [self.x0, self.y0, self.x1, self.y1]


@dataclass(frozen=True)
class CropQualityReport:
    width_px: int | None = None
    height_px: int | None = None
    page_width_px: int | None = None
    page_height_px: int | None = None
    area_ratio: float | None = None
    content_density: float | None = None
    min_short_edge_px: int = MIN_CROP_SHORT_EDGE
    max_area_ratio: float = MAX_CROP_AREA_RATIO
    touches_page_edge: bool = False
    header_footer_band_intersection: bool = False
    low_resolution: bool = False
    degraded_page_quality: bool = False
    passed: bool = True
    failure_reason: str | None = None

    def as_json(self) -> dict[str, object]:
        return {
            "widthPx": self.width_px,
            "heightPx": self.height_px,
            "pageWidthPx": self.page_width_px,
            "pageHeightPx": self.page_height_px,
            "areaRatio": self.area_ratio,
            "contentDensity": self.content_density,
            "minShortEdgePx": self.min_short_edge_px,
            "maxAreaRatio": self.max_area_ratio,
            "touchesPageEdge": self.touches_page_edge,
            "headerFooterBandIntersection": self.header_footer_band_intersection,
            "lowResolution": self.low_resolution,
            "degradedPageQuality": self.degraded_page_quality,
            "passed": self.passed,
            "failureReason": self.failure_reason,
        }


@dataclass(frozen=True)
class VisualInputPlan:
    mode: VisualInputMode
    intended_scope: VisualInputScope
    effective_scope: VisualInputScope
    page_id: UUID | None
    page_number: int | None
    source_page_image_sha256: str | None
    input_sha256: str | None
    bbox: PixelBBox | None = None
    original_bbox: list[float] | None = None
    expanded_bbox: PixelBBox | None = None
    bbox_basis: BBoxBasis = "unknown"
    bbox_confidence: float | None = None
    rotation_policy: RotationPolicy = "unknown"
    expansion_policy: tuple[str, ...] = ()
    fallback_reason: str | None = None
    crop_quality: CropQualityReport = field(default_factory=CropQualityReport)
    continuation_group: str | None = None
    selected_attempt_index: int = 0

    def as_json(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "scope": self.effective_scope,
            "intendedScope": self.intended_scope,
            "pageId": str(self.page_id) if self.page_id else None,
            "pageNumber": self.page_number,
            "sourcePageImageSha256": self.source_page_image_sha256,
            "inputSha256": self.input_sha256,
            "bbox": self.bbox.as_list() if self.bbox else None,
            "originalBbox": self.original_bbox,
            "expandedBbox": self.expanded_bbox.as_list() if self.expanded_bbox else None,
            "bboxBasis": self.bbox_basis,
            "bboxConfidence": self.bbox_confidence,
            "rotationPolicy": self.rotation_policy,
            "expansionPolicy": list(self.expansion_policy),
            "fallbackReason": self.fallback_reason,
            "cropQuality": self.crop_quality.as_json(),
            "continuationGroup": self.continuation_group,
            "selectedAttemptIndex": self.selected_attempt_index,
        }


@dataclass(frozen=True)
class PlannedImageInput:
    image_input: ModelImageInput
    plan: VisualInputPlan


@dataclass(frozen=True)
class VisualInputAttempt:
    plan: VisualInputPlan | None
    useful: bool | None
    failure_reason: str | None = None

    def as_json(self) -> dict[str, object]:
        return {
            "visualInputPlan": self.plan.as_json() if self.plan else None,
            "useful": self.useful,
            "failureReason": self.failure_reason,
        }


@dataclass(frozen=True)
class VisualInputDecision:
    inputs: tuple[PlannedImageInput, ...]
    attempts: tuple[dict[str, object], ...] = ()

    @property
    def model_inputs(self) -> tuple[ModelImageInput, ...]:
        return tuple(item.image_input for item in self.inputs)

    @property
    def primary_plan(self) -> VisualInputPlan | None:
        return self.inputs[0].plan if self.inputs else None

    def as_json(self) -> dict[str, object]:
        return {
            "inputs": [item.plan.as_json() for item in self.inputs],
            "attempts": list(self.attempts),
        }
