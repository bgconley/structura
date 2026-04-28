from __future__ import annotations

from lib.extraction.gateways._vision import VisionClientProtocol, VisionExtractionGateway
from lib.model_runtime.profiles import QWEN_VL_PROFILE


class QwenVLExtractionGateway(VisionExtractionGateway):
    prompt_version = "phase8_5-qwen-handwriting-v1"
    profile_name = QWEN_VL_PROFILE

    def __init__(self, *, client: VisionClientProtocol) -> None:
        super().__init__(client=client)
