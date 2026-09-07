"""Historical v1 identities pinned BEFORE additive v2 parser/reader changes.

This is the committed source-authored evaluation fixture, not regenerated model
output. Both canonical hashes and field-order-sensitive serialization are pinned.
"""

import hashlib
import json
from pathlib import Path

from lib.document_parsing.model_output import PageParseOutput
from lib.document_processing.models import content_digest
from lib.evaluation.captures import DocumentCapture


def test_v1_configuration_invocation_structure_capture_and_checkpoint_bytes_remain_exact():
    capture = DocumentCapture.model_validate_json(
        Path("tests/fixtures/evaluation/capture.json").read_text()
    )
    expected = (
        (
            capture.configuration,
            "cc31578131d1b5cbd0894485f68db412fee787f84f6fb7a3ecd536a2e486d89d",
            "9164fdde4d2a70cf6934c0f3b9fac21ebfcdf22586bde958525270729d56454e",
        ),
        (
            capture.structure.invocations[0],
            "3cc075a8601f409500d26b1c106f6e8aa106546f688c85af3bcea9a6e68669b5",
            "a1c4298bf4d5328ef38418e883bcd0688d887f47229effd765ccb10fb9665d16",
        ),
        (
            capture.structure,
            "ef1a9a3d2f6a4b97b309f225fcf32abfffd1fe943d28d5b7a058bd2dc63c9e41",
            "5e99f0f6f1fefbe5ba7af3340a2219d52f5fcaea56c39c9aeb6ed61349d4cbfb",
        ),
        (
            capture,
            "acbb756da4511852f9be6f62b11212cbb53c5ed351da3623f8fff3a9013e58fe",
            "69c417d264deebb5e68167eb74a753c0e78daf3d848cc23ef2555559053908d3",
        ),
    )
    for model, canonical_sha256, serialized_sha256 in expected:
        assert content_digest(model.model_dump(mode="json")) == canonical_sha256
        assert hashlib.sha256(model.model_dump_json().encode()).hexdigest() == serialized_sha256
        assert json.loads(model.model_dump_json()) == model.model_dump(mode="json")
    checkpoint_hashes = tuple(
        content_digest(
            {
                "page": page.model_dump(mode="json"),
                "invocation": invocation.model_dump(mode="json"),
                "raw": raw.raw_output,
            }
        )
        for page, invocation, raw in zip(
            capture.structure.pages, capture.structure.invocations, capture.raw_pages, strict=True
        )
    )
    assert checkpoint_hashes == (
        "606dd55438c66875e49f7674bf9a32763af8d806a4366805f370c642bf977a61",
        "eae3d6c88ca8b69cab9868b477f0f370e0fece73479f8633b19cbd9438f2103f",
    )
    assert content_digest(PageParseOutput.model_json_schema()) == (
        "e347d8709702470b54eca0b8678285db5436d6f8fb27ec0da232c486f51fa54f"
    )
