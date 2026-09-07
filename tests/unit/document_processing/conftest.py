from __future__ import annotations

import json
from dataclasses import dataclass
from threading import Event
from uuid import uuid4

import pytest
from PIL import Image

from lib.document_processing.checkpoint_validation import validate_checkpoint
from lib.document_processing.models import ProcessingBinding, content_digest
from lib.document_processing.parser_configuration import (
    DeclaredParserDeployment,
    parser_configuration,
)
from lib.document_processing.service import DocumentProcessingService
from lib.document_processing.source_repository import RegisteredParseSource
from lib.jobs.ownership import JobAttempt, job_attempt_scope
from lib.model_runtime.contracts import VisionGenerateResponse
from lib.storage import ObjectStorage


class PageClient:
    def __init__(self, *, after_generate=lambda: None, fail_page=None):
        self.calls = []
        self.after_generate = after_generate
        self.fail_page = fail_page

    def generate(self, request):
        number = int(request.prompt.split("Parse page ")[1].split(" ")[0])
        self.calls.append(number)
        if number == self.fail_page:
            raise RuntimeError("Controlled model outage")
        data = {
            "page_number": number,
            "state": "processed",
            "diagnostics": [],
            "elements": [
                {
                    "kind": "paragraph",
                    "text": f"Source page {number}",
                    "parent_index": None,
                    "table": None,
                    "bbox": {"left": 0, "top": 0, "right": 1000, "bottom": 1000},
                }
            ],
        }
        self.after_generate()
        return VisionGenerateResponse(
            profile_name=request.profile_name,
            model_name="qwen38-27b-bf16-oxcart",
            model_version="explicit-test-fixture",
            source_engine="qwen3_8_27b",
            prompt_version=request.prompt_version,
            raw_text=json.dumps(data),
            normalized_json=data,
            confidence_json={},
            input_sha256=tuple(image.sha256 for image in request.image_inputs),
            latency_ms=0,
            finish_reason="stop",
            structured_output_used=True,
        )


class MemoryProcessingService(DocumentProcessingService):
    def __init__(self, configuration):
        self.configuration = configuration
        self.inventory = None
        self.checkpoints = []
        self.structure = None
        self.active = True

    def assert_authority(self, binding):
        if not self.active:
            raise RuntimeError("Controlled authority loss")

    def initialize_inventory(self, binding, inventory):
        self.assert_authority(binding)
        if self.inventory is not None:
            assert self.inventory == inventory
        self.inventory = inventory

    def load_checkpoints(self, binding):
        self.assert_authority(binding)
        return tuple(self.checkpoints)

    def checkpoint(self, binding, checkpoint):
        self.assert_authority(binding)
        validate_checkpoint(
            checkpoint,
            generation_id=binding.parse_generation_id,
            inventory=self.inventory,
            configuration=self.configuration,
        )
        assert checkpoint.page.page_number not in [
            item.page.page_number for item in self.checkpoints
        ]
        self.checkpoints.append(checkpoint)

    def seal(self, binding, structure):
        self.assert_authority(binding)
        assert len(self.checkpoints) == len(self.inventory.pages)
        if self.structure is not None:
            assert self.structure == structure
        self.structure = structure
        return content_digest(structure.model_dump(mode="json"))


@dataclass
class ExecutionHarness:
    binding: ProcessingBinding
    registered: RegisteredParseSource
    storage: ObjectStorage
    service: MemoryProcessingService
    deployment: DeclaredParserDeployment

    def scope(self):
        return job_attempt_scope(JobAttempt(uuid4(), uuid4()), Event())


@pytest.fixture
def execution(tmp_path, monkeypatch):
    def build(page_count=2, *, mime_type="image/tiff", render_scale=2):
        storage = ObjectStorage(
            canonical_root=tmp_path / "canonical",
            derived_root=tmp_path / "derived",
            export_root=tmp_path / "exports",
        )
        path = tmp_path / f"{page_count}.tiff"
        frames = [Image.new("RGB", (10, 10), (number % 256, 0, 0)) for number in range(page_count)]
        try:
            frames[0].save(path, save_all=True, append_images=frames[1:])
        finally:
            for frame in frames:
                frame.close()
        stored = storage.store_bytes(path.read_bytes(), kind="canonical", role="original")
        deployment = DeclaredParserDeployment(
            mode="fixture", served_model="qwen38-27b-bf16-oxcart", revision="synthetic-v1"
        )
        config = parser_configuration(deployment, mime_type, render_scale=render_scale)
        source = RegisteredParseSource(
            original_asset_id=uuid4(),
            original_sha256=stored.sha256,
            uri=stored.uri,
            mime_type=mime_type,
            byte_size=stored.byte_size,
            configuration=config,
        )
        monkeypatch.setattr(
            "lib.document_processing.parse_execution.load_processing_source", lambda binding: source
        )
        return ExecutionHarness(
            ProcessingBinding(uuid4(), uuid4(), uuid4()),
            source,
            storage,
            MemoryProcessingService(config),
            deployment,
        )

    return build
