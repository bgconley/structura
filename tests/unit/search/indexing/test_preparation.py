from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest

from lib.document_parsing.source_adapter import DocumentSource
from lib.document_processing.models import ProcessingBinding
from lib.document_processing.parser_configuration import (
    DeclaredParserDeployment,
    parser_configuration,
)
from lib.jobs.ownership import JobAttempt, job_attempt_scope
from lib.search.indexing.configuration import index_configuration
from lib.search.indexing.errors import IndexCandidateError
from lib.search.indexing.execution_inputs import prepare_index_candidate
from lib.search.indexing.models import IndexBinding, IndexPreparationSource, PreparedIndexSnapshot
from lib.search.indexing.projection import project_inputs
from lib.search.indexing.render_verification import read_verified_render
from lib.search.indexing.service import CandidateIndexService
from lib.storage import ObjectStorage


class PreparationStore:
    def __init__(self, snapshot, index_id, storage):
        self.snapshot = snapshot
        self.index_id = index_id
        self.storage = storage
        self.prepared = None
        self.authority_checks = 0

    def load_preparation(self, binding):
        return self.snapshot

    def load_prepared(self, binding):
        assert self.prepared is not None
        return self.prepared

    def assert_authority(self, binding):
        self.authority_checks += 1

    def prepare(self, binding, assets=()):
        for asset in assets:
            read_verified_render(asset, self.storage)
        manifest = project_inputs(
            self.snapshot.structure,
            index_id=self.index_id,
            configuration=self.snapshot.configuration,
            assets=assets,
        )
        self.prepared = PreparedIndexSnapshot(self.snapshot.configuration, manifest, assets, ())
        self.snapshot = replace(self.snapshot, prepared=True)
        return manifest


def preparation_fixture(structure, tmp_path):
    storage = ObjectStorage(
        canonical_root=tmp_path / "canonical",
        derived_root=tmp_path / "derived",
        export_root=tmp_path / "exports",
    )
    fixture = Path(__file__).resolve().parents[3] / "fixtures/evaluation/original.tiff"
    stored = storage.store_bytes(fixture.read_bytes(), kind="canonical", role="original")
    original = structure.source
    with DocumentSource(
        stored.path,
        asset_id=original.original_asset_id,
        expected_sha256=original.original_sha256,
        mime_type="image/tiff",
    ) as source:
        pages = tuple(
            page.model_copy(update={"source": source.render(page.page_number).identity})
            for page in structure.pages
        )
        structure = structure.model_copy(update={"source": source.inventory, "pages": pages})
    config = index_configuration(model_mode="fixture")
    parser = parser_configuration(
        DeclaredParserDeployment(
            mode="fixture", served_model="qwen38-27b-bf16-oxcart", revision="source-authored-test-1"
        ),
        "image/tiff",
    )
    snapshot = IndexPreparationSource(config, parser, structure, stored.uri, False)
    identity = uuid4()
    service = PreparationStore(snapshot, identity, storage)
    binding = IndexBinding(
        ProcessingBinding(uuid4(), structure.processing_run_id, structure.parse_generation_id),
        identity,
    )
    return service, binding, storage


def test_stages_exact_original_renders_and_prepared_replay_does_not_rerender(
    structure, tmp_path, monkeypatch
):
    from lib.search.indexing import execution_inputs as module

    service, binding, storage = preparation_fixture(structure, tmp_path)
    with job_attempt_scope(JobAttempt(uuid4(), uuid4()), Event()):
        manifest = prepare_index_candidate(binding, storage=storage, service=service)
        assert len(service.prepared.assets) == len(structure.pages)
        assert service.authority_checks == 1 + 2 * len(structure.pages)

        def forbidden_render(*args, **kwargs):
            raise AssertionError("Prepared replay must use retained exact PNG bytes")

        monkeypatch.setattr(module, "DocumentSource", forbidden_render)
        assert prepare_index_candidate(binding, storage=storage, service=service) == manifest


def test_changed_renderer_or_page_descriptor_refuses_staging(structure, tmp_path):
    service, binding, storage = preparation_fixture(structure, tmp_path)
    service.snapshot = replace(
        service.snapshot,
        parse_configuration=service.snapshot.parse_configuration.model_copy(
            update={"renderer_version": "different"}
        ),
    )
    with pytest.raises(IndexCandidateError, match="renderer"):
        prepare_index_candidate(binding, storage=storage, service=service)
    assert service.prepared is None


def test_missing_original_or_wrong_inventory_does_not_prepare_inputs(structure, tmp_path):
    service, binding, storage = preparation_fixture(structure, tmp_path)
    storage.path_for_uri(service.snapshot.original_uri).unlink()
    from lib.document_parsing.source_adapter import DocumentSourceError

    with pytest.raises(DocumentSourceError):
        prepare_index_candidate(binding, storage=storage, service=service)
    assert service.prepared is None


@pytest.mark.parametrize("kind", ["duplicate", "duplicate_page_identity", "oversized"])
def test_external_asset_inventory_is_bounded_before_any_io(structure, tmp_path, monkeypatch, kind):
    from lib.search.indexing import service as module
    from tests.unit.search.indexing.conftest import assets_for

    first, second = assets_for(structure, uuid4())
    assets = (
        (first, second.model_copy(update={"page_id": first.page_id}))
        if kind == "duplicate_page_identity"
        else (first,) * (2 if kind == "duplicate" else 501)
    )
    service = CandidateIndexService(ObjectStorage(derived_root=tmp_path))

    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid inventory must fail before authority or filesystem IO")

    monkeypatch.setattr(service, "assert_authority", forbidden)
    monkeypatch.setattr(module, "read_verified_render", forbidden)
    binding = IndexBinding(ProcessingBinding(uuid4(), uuid4(), uuid4()), uuid4())
    with pytest.raises(IndexCandidateError, match="bound"):
        service.prepare(binding, assets)


@pytest.mark.parametrize("reuse_first", [False, True])
def test_interrupted_staging_cleans_only_created_unreferenced_objects(
    structure, tmp_path, monkeypatch, reuse_first
):
    from lib.search.indexing import execution_inputs as module

    service, binding, storage = preparation_fixture(structure, tmp_path)
    original_path = storage.path_for_uri(service.snapshot.original_uri)
    retained = None
    if reuse_first:
        source = service.snapshot.structure.source
        with DocumentSource(
            original_path,
            asset_id=source.original_asset_id,
            expected_sha256=source.original_sha256,
            mime_type=source.mime_type,
        ) as document:
            retained = storage.store_bytes(
                document.render(1).image_bytes, kind="derived", role="native-index-source"
            )
    second = service.snapshot.structure.pages[1]
    bad = second.model_copy(
        update={"source": second.source.model_copy(update={"image_sha256": "f" * 64})}
    )
    service.snapshot = replace(
        service.snapshot,
        structure=service.snapshot.structure.model_copy(
            update={"pages": (service.snapshot.structure.pages[0], bad)}
        ),
    )
    cleaned = []

    def cleanup(stored):
        cleaned.append(stored)
        if stored.created:
            stored.path.unlink()

    monkeypatch.setattr(module, "cleanup_unreferenced_stored_object", cleanup)
    with pytest.raises(IndexCandidateError, match="descriptor"):
        prepare_index_candidate(binding, storage=storage, service=service)
    assert len(cleaned) == 1 and cleaned[0].created is not reuse_first
    assert original_path.exists() and service.prepared is None
    assert cleaned[0].path.exists() is reuse_first
    if retained:
        assert retained.path.exists()


def test_prepare_failure_cleans_staged_renders_after_service_unwinds(
    structure, tmp_path, monkeypatch
):
    from lib.search.indexing import execution_inputs as module

    service, binding, storage = preparation_fixture(structure, tmp_path)
    state = {"transaction_closed": False}

    def failed_prepare(*args):
        state["transaction_closed"] = True
        raise RuntimeError("Controlled preparation rollback")

    monkeypatch.setattr(service, "prepare", failed_prepare)
    cleaned = []

    def cleanup(stored):
        assert state["transaction_closed"]
        cleaned.append(stored)

    monkeypatch.setattr(module, "cleanup_unreferenced_stored_object", cleanup)
    with pytest.raises(RuntimeError, match="rollback"):
        prepare_index_candidate(binding, storage=storage, service=service)
    assert len(cleaned) == 2 and all(stored.created for stored in cleaned)
