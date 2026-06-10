"""Pure Qwen semantic input-budget estimation shared by canary and live path.

These estimators were extracted from ``scripts/gpu/run_phase8_5_semantic_canary.py``
(token-budget reporting) so the live Qwen gateway can compute the same
conservative pre-dispatch estimate: rendered page-image dimensions to
visual-token estimates, text-token estimates for prompt (including Docling
context) and response schema, plus the requested output budget. The live
gateway turns the estimate into warning telemetry only; dispatch behavior
never changes here.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from lib.model_runtime.profiles import ModelProfile

DEFAULT_INPUT_BUDGET_WARN_FRACTION = 0.9
DEFAULT_VISUAL_TOKEN_SPATIAL_COMPRESSION = 32
INPUT_BUDGET_WARNING_KIND = "qwen_semantic_input_budget_pressure"


def estimate_text_tokens(value: str) -> int:
    if not value:
        return 0
    return math.ceil(len(value) / 4)


def visual_token_estimate(*, width: int, height: int, compression: int) -> int:
    return math.ceil((width * height) / (compression * compression))


def qwen_grid_estimate(
    *,
    width: int,
    height: int,
    compression: int,
    min_pixels: int | None,
    max_pixels: int | None,
) -> dict[str, int]:
    pixels = width * height
    target_pixels = pixels
    if max_pixels and target_pixels > max_pixels:
        target_pixels = max_pixels
    if min_pixels and target_pixels < min_pixels:
        target_pixels = min_pixels
    scale = math.sqrt(target_pixels / pixels) if pixels > 0 else 1.0
    resized_width = max(1, round(width * scale))
    resized_height = max(1, round(height * scale))
    grid_width = max(1, math.ceil(resized_width / compression))
    grid_height = max(1, math.ceil(resized_height / compression))
    if max_pixels:
        max_visual_tokens = max(1, max_pixels // (compression * compression))
        while grid_width * grid_height > max_visual_tokens:
            if grid_width >= grid_height and grid_width > 1:
                grid_width -= 1
            elif grid_height > 1:
                grid_height -= 1
            else:
                break
        resized_width = min(resized_width, grid_width * compression)
        resized_height = min(resized_height, grid_height * compression)
    return {
        "resized_width_px": resized_width,
        "resized_height_px": resized_height,
        "grid_width": grid_width,
        "grid_height": grid_height,
        "visual_tokens": grid_width * grid_height,
    }


def image_dimensions(image_bytes: bytes) -> tuple[int, int] | None:
    if len(image_bytes) >= 24 and image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return (
            int.from_bytes(image_bytes[16:20], "big"),
            int.from_bytes(image_bytes[20:24], "big"),
        )
    if len(image_bytes) >= 4 and image_bytes.startswith(b"\xff\xd8"):
        return _jpeg_dimensions(image_bytes)
    return None


@dataclass(frozen=True)
class ProfileVisualTokenBudget:
    compression: int
    min_visual_tokens: int
    max_visual_tokens: int

    @property
    def min_pixels(self) -> int | None:
        if not self.min_visual_tokens:
            return None
        return self.min_visual_tokens * self.compression * self.compression

    @property
    def max_pixels(self) -> int | None:
        if not self.max_visual_tokens:
            return None
        return self.max_visual_tokens * self.compression * self.compression


def profile_visual_token_budget(profile: ModelProfile) -> ProfileVisualTokenBudget:
    return ProfileVisualTokenBudget(
        compression=(
            profile.visual_token_spatial_compression or DEFAULT_VISUAL_TOKEN_SPATIAL_COMPRESSION
        ),
        min_visual_tokens=profile.visual_token_min_per_image or 0,
        max_visual_tokens=profile.visual_token_max_per_image or 0,
    )


def image_visual_token_estimate(
    image_bytes: bytes,
    *,
    budget: ProfileVisualTokenBudget,
) -> tuple[int, bool]:
    """Per-image visual-token estimate plus whether dimensions were readable.

    Unreadable image headers fall back to the profile's per-image visual-token
    maximum so the pre-dispatch estimate stays conservative.
    """
    dimensions = image_dimensions(image_bytes)
    if dimensions is None:
        return budget.max_visual_tokens, False
    width, height = dimensions
    grid = qwen_grid_estimate(
        width=width,
        height=height,
        compression=budget.compression,
        min_pixels=budget.min_pixels,
        max_pixels=budget.max_pixels,
    )
    return grid["visual_tokens"], True


@dataclass(frozen=True)
class SemanticInputBudgetEstimate:
    profile_name: str
    max_model_len: int | None
    prompt_token_estimate: int
    schema_token_estimate: int
    visual_token_estimate: int
    requested_output_tokens: int
    image_count: int
    images_without_dimensions: int

    @property
    def conservative_total_token_estimate(self) -> int:
        return (
            self.prompt_token_estimate
            + self.schema_token_estimate
            + self.visual_token_estimate
            + self.requested_output_tokens
        )

    def as_json(self) -> dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "max_model_len": self.max_model_len,
            "prompt_token_estimate": self.prompt_token_estimate,
            "schema_token_estimate": self.schema_token_estimate,
            "visual_token_estimate": self.visual_token_estimate,
            "requested_output_tokens": self.requested_output_tokens,
            "image_count": self.image_count,
            "images_without_dimensions": self.images_without_dimensions,
            "conservative_total_token_estimate": self.conservative_total_token_estimate,
        }


def estimate_semantic_input_budget(
    *,
    profile: ModelProfile,
    prompt: str,
    response_json_schema: dict[str, Any] | None,
    image_bytes_inputs: Sequence[bytes],
    requested_output_tokens: int,
) -> SemanticInputBudgetEstimate:
    budget = profile_visual_token_budget(profile)
    visual_tokens = 0
    images_without_dimensions = 0
    for image_bytes in image_bytes_inputs:
        estimate, dimensions_known = image_visual_token_estimate(image_bytes, budget=budget)
        visual_tokens += estimate
        if not dimensions_known:
            images_without_dimensions += 1
    schema_token_estimate = (
        estimate_text_tokens(json.dumps(response_json_schema, sort_keys=True))
        if response_json_schema
        else 0
    )
    return SemanticInputBudgetEstimate(
        profile_name=profile.name,
        max_model_len=profile.max_model_len,
        prompt_token_estimate=estimate_text_tokens(prompt),
        schema_token_estimate=schema_token_estimate,
        visual_token_estimate=visual_tokens,
        requested_output_tokens=requested_output_tokens,
        image_count=len(image_bytes_inputs),
        images_without_dimensions=images_without_dimensions,
    )


def input_budget_warning(
    estimate: SemanticInputBudgetEstimate,
    *,
    warn_fraction: float = DEFAULT_INPUT_BUDGET_WARN_FRACTION,
) -> dict[str, Any] | None:
    """Structured warning when the conservative estimate exceeds the threshold.

    Returns None when the profile has no ``max_model_len`` or when
    ``warn_fraction`` is non-positive (treated as disabled).
    """
    if not estimate.max_model_len or warn_fraction <= 0:
        return None
    threshold_tokens = math.floor(estimate.max_model_len * warn_fraction)
    if estimate.conservative_total_token_estimate <= threshold_tokens:
        return None
    return {
        "kind": INPUT_BUDGET_WARNING_KIND,
        "warn_fraction": warn_fraction,
        "threshold_tokens": threshold_tokens,
        **estimate.as_json(),
    }


def _jpeg_dimensions(image_bytes: bytes) -> tuple[int, int] | None:
    index = 2
    while index + 9 < len(image_bytes):
        if image_bytes[index] != 0xFF:
            index += 1
            continue
        marker = image_bytes[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(image_bytes):
            return None
        segment_length = int.from_bytes(image_bytes[index : index + 2], "big")
        if segment_length < 2 or index + segment_length > len(image_bytes):
            return None
        if marker in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            height = int.from_bytes(image_bytes[index + 3 : index + 5], "big")
            width = int.from_bytes(image_bytes[index + 5 : index + 7], "big")
            return width, height
        index += segment_length
    return None
