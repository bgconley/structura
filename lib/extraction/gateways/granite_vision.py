from __future__ import annotations

from lib.extraction.gateways._vision import VisionClientProtocol, VisionExtractionGateway
from lib.model_runtime.profiles import GRANITE_VISION_PROFILE


class GraniteVisionExtractionGateway(VisionExtractionGateway):
    prompt_version = "phase8_5-granite-structured-v1"
    profile_name = GRANITE_VISION_PROFILE
    max_image_inputs = 1

    def __init__(self, *, client: VisionClientProtocol) -> None:
        super().__init__(client=client)
