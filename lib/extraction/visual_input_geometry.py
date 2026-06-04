from __future__ import annotations

from typing import Any, cast

from lib.extraction.visual_input_types import (
    BBoxBasis,
    PixelBBox,
    RotationPolicy,
    VisualInputScope,
)


def bbox_to_pixels(
    bbox: list[float],
    basis: BBoxBasis,
    *,
    page_width_px: int | None,
    page_height_px: int | None,
    page_width_points: float | None = None,
    page_height_points: float | None = None,
) -> PixelBBox | None:
    if page_width_px is None or page_height_px is None:
        return None
    x0, y0, x1, y1 = bbox
    if basis == "pdf_points":
        if not page_width_points or not page_height_points:
            return None
        x_scale = page_width_px / page_width_points
        y_scale = page_height_px / page_height_points
        pixel = PixelBBox(
            int(round(x0 * x_scale)),
            int(round(y0 * y_scale)),
            int(round(x1 * x_scale)),
            int(round(y1 * y_scale)),
        )
    elif basis == "normalized_1000":
        pixel = PixelBBox(
            int(round(x0 / 1000 * page_width_px)),
            int(round(y0 / 1000 * page_height_px)),
            int(round(x1 / 1000 * page_width_px)),
            int(round(y1 / 1000 * page_height_px)),
        )
    elif basis == "image_pixels":
        pixel = PixelBBox(int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1)))
    else:
        return None
    return clamp_bbox(pixel, page_width_px, page_height_px)


def expanded_bbox(
    bbox: PixelBBox,
    *,
    page_width_px: int | None,
    page_height_px: int | None,
    semantic_type: str,
    granite_task: str | None,
    scope: VisualInputScope,
    crop_first_types: set[str] | frozenset[str],
) -> tuple[PixelBBox, tuple[str, ...]]:
    if page_width_px is None or page_height_px is None:
        return bbox, ()
    policies: list[str] = ["safe_margin_pad"]
    pad_x = max(12, int(round(bbox.width * 0.08)))
    pad_y = max(12, int(round(bbox.height * 0.08)))
    x0 = bbox.x0 - pad_x
    y0 = bbox.y0 - pad_y
    x1 = bbox.x1 + pad_x
    y1 = bbox.y1 + pad_y
    if scope == "table_crop" or semantic_type in crop_first_types:
        policies.extend(["table_header_band", "left_label_band"])
        y0 -= max(24, int(round(bbox.height * 0.25)))
        x0 -= max(24, int(round(bbox.width * 0.08)))
    elif granite_task == "kvp":
        policies.extend(["left_label_band", "top_label_band"])
        y0 -= max(18, int(round(bbox.height * 0.20)))
        x0 -= max(36, int(round(bbox.width * 0.20)))
    clamped = clamp_bbox(PixelBBox(x0, y0, x1, y1), page_width_px, page_height_px)
    return clamped or bbox, tuple(dict.fromkeys(policies))


def clamp_bbox(bbox: PixelBBox, width: int, height: int) -> PixelBBox | None:
    x0 = max(0, min(width, bbox.x0))
    y0 = max(0, min(height, bbox.y0))
    x1 = max(0, min(width, bbox.x1))
    y1 = max(0, min(height, bbox.y1))
    if x1 <= x0 or y1 <= y0:
        return None
    return PixelBBox(x0=x0, y0=y0, x1=x1, y1=y1)


def normalize_bbox(value: Any) -> list[float] | None:
    if isinstance(value, list) and len(value) == 4:
        return [float(item) for item in value]
    if isinstance(value, tuple) and len(value) == 4:
        return [float(item) for item in value]
    if isinstance(value, dict):
        for keys in (
            ("l", "t", "r", "b"),
            ("x0", "y0", "x1", "y1"),
            ("left", "top", "right", "bottom"),
        ):
            if all(key in value for key in keys):
                return [float(value[key]) for key in keys]
        if all(key in value for key in ("x", "y", "width", "height")):
            x = float(value["x"])
            y = float(value["y"])
            return [x, y, x + float(value["width"]), y + float(value["height"])]
        nested = value.get("bbox")
        if nested is not None:
            return normalize_bbox(nested)
    return None


def basis_from_metadata(metadata: dict[str, Any]) -> BBoxBasis | None:
    for key in ("visual_bbox_basis", "bbox_basis", "coordinate_basis"):
        value = metadata.get(key)
        if value in {"pdf_points", "image_pixels", "normalized_1000"}:
            return cast(BBoxBasis, value)
    return None


def basis_from_bbox(value: Any) -> BBoxBasis:
    if isinstance(value, dict):
        basis = value.get("basis") or value.get("bbox_basis") or value.get("coordinate_basis")
        if basis in {"pdf_points", "image_pixels", "normalized_1000"}:
            return cast(BBoxBasis, basis)
    return "unknown"


def rotation_policy(rotation_degrees: int | None) -> RotationPolicy:
    rotation = (rotation_degrees or 0) % 360
    if rotation == 0:
        return "upright"
    if rotation == 90:
        return "rotate_90"
    if rotation == 180:
        return "rotate_180"
    if rotation == 270:
        return "rotate_270"
    return "unknown"


def crop_box(bbox: PixelBBox) -> tuple[float, float, float, float]:
    return (float(bbox.x0), float(bbox.y0), float(bbox.x1), float(bbox.y1))
