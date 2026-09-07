"""Two bounded synthetic calls through Structura; never changes model serving."""

from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.config import get_settings  # noqa: E402
from lib.model_runtime.contracts import (  # noqa: E402
    ModelImageInput,
    TextGenerateRequest,
    VisionGenerateRequest,
)
from lib.model_runtime.http_client import ModelRuntimeError  # noqa: E402
from lib.model_runtime.ingestion_clients import (  # noqa: E402
    ingestion_text_client,
    ingestion_vision_client,
)


def main() -> int:
    settings = get_settings()
    schema = {
        "type": "object",
        "properties": {"reference": {"type": "string"}, "amount": {"type": "string"}},
        "required": ["reference", "amount"],
        "additionalProperties": False,
    }
    options: dict[str, Any] = {
        "profile_name": settings.model_ingestion_profile,
        "prompt_version": "completion-ingestion-probe-v1",
        "response_schema_name": "synthetic_receipt_probe.v1",
        "response_json_schema": schema,
        "max_output_tokens": 256,
        "temperature": 0.0,
        "timeout_seconds": min(settings.model_ingestion_timeout_seconds, 60),
    }
    page = Image.new("RGB", (800, 300), "white")
    drawing = ImageDraw.Draw(page)
    font = ImageFont.load_default(size=34)
    drawing.text(
        (30, 40), "SYNTHETIC RECEIPT\nReference: V-902\nAmount: 27.15", fill="black", font=font
    )
    buffer = io.BytesIO()
    page.save(buffer, format="PNG")
    pixels = buffer.getvalue()
    try:
        text = ingestion_text_client(settings).generate(
            TextGenerateRequest(
                **options,
                prompt=(
                    "Read this synthetic receipt. Return only the reference and amount exactly: "
                    "Reference T-731; Amount 42.80."
                ),
            )
        )
        vision = ingestion_vision_client(settings).generate(
            VisionGenerateRequest(
                **options,
                prompt=(
                    "Read the attached synthetic receipt image. "
                    "Return only its reference and amount exactly as printed."
                ),
                image_inputs=(
                    ModelImageInput(pixels, "image/png", hashlib.sha256(pixels).hexdigest()),
                ),
            )
        )
    except ModelRuntimeError as error:
        print(json.dumps({"passed": False, "error_class": type(error).__name__}))
        return 1
    results = []
    for modality, response, expected in (
        ("text", text, {"reference": "T-731", "amount": "42.80"}),
        ("image", vision, {"reference": "V-902", "amount": "27.15"}),
    ):
        results.append(
            {
                "modality": modality,
                "passed": response.normalized_json == expected,
                "profile": response.profile_name,
                "served_model": response.model_name,
                "source_engine": response.source_engine,
                "latency_ms": response.latency_ms,
                "finish_reason": response.finish_reason,
                "structured_output_used": response.structured_output_used,
            }
        )
    passed = all(result["passed"] for result in results)
    print(json.dumps({"passed": passed, "synthetic": True, "requests": results}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
