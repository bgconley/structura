from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lib.document_processing.models import content_digest
from lib.document_processing.parse_execution import execute_parse_candidate
from lib.evidence.manifest import completion_manifest, expected_render_set, validate_asset
from lib.evidence.media import snapshot_render
from lib.evidence.models import RenderSetBinding, RenderSetSnapshot, render_set_id
from tests.unit.document_processing.conftest import PageClient, execution  # noqa: F401


class MemoryEvidenceWriter:
    """Storage executor port; no database or live provenance is implied."""

    def __init__(self, harness):
        self.harness = harness
        structure = harness.service.structure
        self.row = {
            "id": harness.binding.processing_run_id,
            "processing_run_id": harness.binding.processing_run_id,
            "document_id": harness.binding.document_id,
            "parse_generation_id": harness.binding.parse_generation_id,
            "parse_state": "sealed",
            "run_status": "sealed",
            "structure_version": structure.schema_version,
            "structure_json": structure.model_dump(mode="json"),
            "structure_sha256": content_digest(structure.model_dump(mode="json")),
            "inventory_json": structure.source.model_dump(mode="json"),
            "inventory_sha256": content_digest(structure.source.model_dump(mode="json")),
            "config_json": harness.registered.configuration.model_dump(mode="json"),
            "config_sha256": harness.registered.configuration.fingerprint,
            "original_asset_id": harness.registered.original_asset_id,
            "original_sha256": harness.registered.original_sha256,
            "page_count": len(structure.pages),
            "observed_at": datetime.now(UTC),
            "render_set_state": "building",
            "render_set_sha256": None,
        }
        self.checkpoints = [
            {
                "page_id": c.page.id,
                "page_number": c.page.page_number,
                "page_json": c.page.model_dump(mode="json"),
                "invocation_json": c.invocation.model_dump(mode="json"),
                "raw_output": c.raw_output,
                "content_sha256": content_digest(
                    {
                        "page": c.page.model_dump(mode="json"),
                        "invocation": c.invocation.model_dump(mode="json"),
                        "raw": c.raw_output,
                    }
                ),
            }
            for c in harness.service.checkpoints
        ]
        self.expected = expected_render_set(self.row, self.checkpoints)
        self.binding = RenderSetBinding(
            harness.binding, render_set_id(harness.binding.parse_generation_id)
        )
        self.assets = []
        self.state = "building"
        self.completion = None
        self.active = True

    def assert_authority(self, binding):
        assert binding == self.binding
        if not self.active:
            raise RuntimeError("Controlled authority loss")

    def start(self, processing):
        assert processing == self.binding.processing
        self.assert_authority(self.binding)
        return self.binding

    def snapshot(self, binding):
        self.assert_authority(binding)
        return RenderSetSnapshot(self.expected, tuple(self.assets), self.state, self.completion)

    def execution_source(self, binding):
        self.assert_authority(binding)
        return {
            **self.row,
            "uri": self.harness.registered.uri,
            "mime_type": self.harness.registered.mime_type,
            "byte_size": self.harness.registered.byte_size,
            "sha256": self.harness.registered.original_sha256,
        }

    def checkpoint(self, binding, asset):
        self.assert_authority(binding)
        validate_asset(asset, self.expected)
        verified = snapshot_render(asset, self.harness.storage)
        verified.close()
        self.assets.append(asset)
        return asset.fingerprint

    def seal(self, binding):
        self.assert_authority(binding)
        for asset in self.assets:
            snapshot_render(asset, self.harness.storage).close()
        manifest = completion_manifest(self.expected, tuple(self.assets))
        self.completion = content_digest(manifest)
        self.state = "sealed"
        return manifest

    def read_row(self, offset=0, limit=1, include_content=False, **kwargs):
        pages = []
        for i in range(offset, min(offset + limit, len(self.expected.pages))):
            c = self.checkpoints[i]
            asset = next((a for a in self.assets if a.page_number == i + 1), None)
            pages.append(
                {
                    "page_id": str(c["page_id"]),
                    "page_number": i + 1,
                    "source_page": self.row["inventory_json"]["pages"][i],
                    "parse_state": c["page_json"]["state"],
                    "raster": self.expected.pages[i].render.model_dump(mode="json"),
                    "checkpoint_sha256": c["content_sha256"],
                    "expected_page": self.expected.pages[i].model_dump(mode="json"),
                    "asset": asset.model_dump(mode="json") if asset else None,
                    "asset_sha256": asset.fingerprint if asset else None,
                    "asset_id": str(asset.id) if asset else None,
                    "asset_page_id": str(asset.page_id) if asset else None,
                    "asset_page_number": asset.page_number if asset else None,
                    "page_json": c["page_json"] if include_content else None,
                    "invocation_json": c["invocation_json"] if include_content else None,
                    "raw_output": c["raw_output"] if include_content else None,
                    "chunks": [
                        v for v in self.row["structure_json"]["chunks"] if v["page_number"] == i + 1
                    ]
                    if include_content
                    else None,
                }
            )
        return {
            **self.row,
            "render_set_state": self.state,
            "render_set_sha256": self.expected.fingerprint,
            "pages": pages,
        }


@pytest.fixture
def retained(execution):  # noqa: F811
    harness = execution(3)
    with harness.scope():
        execute_parse_candidate(
            harness.binding,
            storage=harness.storage,
            client=PageClient(),
            deployment=harness.deployment,
            service=harness.service,
        )
    return harness, MemoryEvidenceWriter(harness)
