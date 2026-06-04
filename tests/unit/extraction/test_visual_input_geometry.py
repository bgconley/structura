from __future__ import annotations

from lib.extraction.visual_input_geometry import (
    basis_from_metadata,
    bbox_to_pixels,
    normalize_bbox,
    rotation_policy,
)
from lib.extraction.visual_input_types import PixelBBox


def test_visual_input_geometry_maps_pdf_points_to_pixels() -> None:
    bbox = normalize_bbox({"l": 50, "t": 100, "r": 250, "b": 300})

    assert bbox == [50.0, 100.0, 250.0, 300.0]
    assert basis_from_metadata({"bbox_basis": "pdf_points"}) == "pdf_points"
    assert rotation_policy(90) == "rotate_90"
    assert bbox is not None
    assert bbox_to_pixels(
        bbox,
        "pdf_points",
        page_width_px=1200,
        page_height_px=1600,
        page_width_points=600,
        page_height_points=800,
    ) == PixelBBox(100, 200, 500, 600)
