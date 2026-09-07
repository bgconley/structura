from __future__ import annotations

import pytest

from lib.evidence.models import RetainedPageAsset, source_render_id
from lib.evidence.write_service import RetainedEvidenceWriter
from tests.integration.search.indexing.conftest import candidate_source, processing  # noqa: F401


@pytest.fixture
def evidence(candidate_source):  # noqa: F811
    harness, run, claimed, index, _, stored = candidate_source
    writer = RetainedEvidenceWriter(index.storage)
    with harness.scope(claimed):
        binding = writer.start(run.binding)
        expected = writer.snapshot(binding).expected
    asset = RetainedPageAsset(
        id=source_render_id(run.binding.parse_generation_id, expected.pages[0].page_id),
        **expected.pages[0].model_dump(),
        uri=stored.uri,
        byte_size=stored.byte_size,
    )
    return harness, run, claimed, writer, binding, asset, stored


def populate(evidence):
    harness, _, claimed, writer, binding, asset, _ = evidence
    with harness.scope(claimed):
        writer.checkpoint(binding, asset)
        writer.seal(binding)
