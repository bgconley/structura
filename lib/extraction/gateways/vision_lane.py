from __future__ import annotations

from typing import Literal

VISION_LANE_NAME = "vision"
GRANITE_VISION_PROVIDER = "granite"
QWEN_VISION_PROVIDER = "qwen"
QWEN_VISION_OBSERVATIONS_SCHEMA = "qwen_vision_observations.v1"

VisionProviderName = Literal["granite", "qwen"]
