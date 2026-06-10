from __future__ import annotations

import json
import math

from lib.model_runtime.profiles import QWEN_SEMANTIC_PROFILE, get_model_profile
from lib.semantic_annotations.input_budget import (
    INPUT_BUDGET_WARNING_KIND,
    SemanticInputBudgetEstimate,
    estimate_semantic_input_budget,
    estimate_text_tokens,
    image_dimensions,
    input_budget_warning,
    profile_visual_token_budget,
    qwen_grid_estimate,
    visual_token_estimate,
)


def _png_bytes(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
    )


def _jpeg_bytes(width: int, height: int) -> bytes:
    return (
        b"\xff\xd8"
        + b"\xff\xc0"
        + (17).to_bytes(2, "big")
        + b"\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x03"
        + b"\x00" * 12
    )


def test_estimate_text_tokens_matches_canary_heuristic() -> None:
    assert estimate_text_tokens("") == 0
    assert estimate_text_tokens("abcd") == 1
    assert estimate_text_tokens("abcde") == 2
    assert estimate_text_tokens("x" * 4000) == 1000


def test_image_dimensions_parses_png_and_jpeg_headers() -> None:
    assert image_dimensions(_png_bytes(1700, 2200)) == (1700, 2200)
    assert image_dimensions(_jpeg_bytes(816, 1056)) == (816, 1056)
    assert image_dimensions(b"not-an-image") is None
    assert image_dimensions(b"") is None


def test_visual_token_estimate_uses_spatial_compression() -> None:
    assert visual_token_estimate(width=3200, height=3200, compression=32) == 10000


def test_qwen_grid_estimate_clamps_to_profile_pixel_bounds() -> None:
    budget = profile_visual_token_budget(get_model_profile(QWEN_SEMANTIC_PROFILE))

    huge = qwen_grid_estimate(
        width=10000,
        height=10000,
        compression=budget.compression,
        min_pixels=budget.min_pixels,
        max_pixels=budget.max_pixels,
    )
    assert huge["visual_tokens"] <= budget.max_visual_tokens

    tiny = qwen_grid_estimate(
        width=64,
        height=64,
        compression=budget.compression,
        min_pixels=budget.min_pixels,
        max_pixels=budget.max_pixels,
    )
    assert tiny["visual_tokens"] >= budget.min_visual_tokens


def test_estimate_semantic_input_budget_sums_components() -> None:
    profile = get_model_profile(QWEN_SEMANTIC_PROFILE)
    schema = {"type": "object", "properties": {"pages": {"type": "array"}}}
    prompt = "p" * 400

    estimate = estimate_semantic_input_budget(
        profile=profile,
        prompt=prompt,
        response_json_schema=schema,
        image_bytes_inputs=[_png_bytes(1700, 2200)],
        requested_output_tokens=6144,
    )

    assert estimate.profile_name == profile.name
    assert estimate.max_model_len == profile.max_model_len
    assert estimate.prompt_token_estimate == 100
    assert estimate.schema_token_estimate == estimate_text_tokens(
        json.dumps(schema, sort_keys=True)
    )
    assert estimate.image_count == 1
    assert estimate.images_without_dimensions == 0
    assert estimate.requested_output_tokens == 6144
    assert estimate.conservative_total_token_estimate == (
        estimate.prompt_token_estimate
        + estimate.schema_token_estimate
        + estimate.visual_token_estimate
        + estimate.requested_output_tokens
    )
    assert estimate.as_json()["conservative_total_token_estimate"] == (
        estimate.conservative_total_token_estimate
    )


def test_unreadable_image_dimensions_fall_back_to_profile_max_visual_tokens() -> None:
    profile = get_model_profile(QWEN_SEMANTIC_PROFILE)

    estimate = estimate_semantic_input_budget(
        profile=profile,
        prompt="prompt",
        response_json_schema=None,
        image_bytes_inputs=[b"opaque-image-bytes"],
        requested_output_tokens=10,
    )

    assert estimate.images_without_dimensions == 1
    assert estimate.visual_token_estimate == profile.visual_token_max_per_image


def _estimate(
    total_minus_output: int,
    *,
    max_model_len: int | None = 32768,
) -> SemanticInputBudgetEstimate:
    return SemanticInputBudgetEstimate(
        profile_name="qwen3-vl-8b-fp8-semantic:v1",
        max_model_len=max_model_len,
        prompt_token_estimate=total_minus_output,
        schema_token_estimate=0,
        visual_token_estimate=0,
        requested_output_tokens=6144,
        image_count=1,
        images_without_dimensions=0,
    )


def test_input_budget_warning_triggers_above_fraction_of_max_model_len() -> None:
    threshold = math.floor(32768 * 0.9)
    over = _estimate(threshold - 6144 + 1)

    warning = input_budget_warning(over, warn_fraction=0.9)

    assert warning is not None
    assert warning["kind"] == INPUT_BUDGET_WARNING_KIND
    assert warning["warn_fraction"] == 0.9
    assert warning["threshold_tokens"] == threshold
    assert warning["conservative_total_token_estimate"] == threshold + 1
    assert warning["max_model_len"] == 32768


def test_input_budget_warning_stays_silent_at_or_below_threshold() -> None:
    threshold = math.floor(32768 * 0.9)
    at_threshold = _estimate(threshold - 6144)

    assert input_budget_warning(at_threshold, warn_fraction=0.9) is None


def test_input_budget_warning_disabled_without_max_model_len_or_fraction() -> None:
    assert input_budget_warning(_estimate(100000, max_model_len=None)) is None
    assert input_budget_warning(_estimate(100000), warn_fraction=0.0) is None
    assert input_budget_warning(_estimate(100000), warn_fraction=-1.0) is None
