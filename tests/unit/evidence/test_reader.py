from __future__ import annotations

from uuid import uuid4

import pytest

from lib.documents.access_policy import DocumentAccessContext
from lib.evidence.errors import EvidenceUnavailable
from lib.evidence.read_service import GenerationEvidenceReader
from lib.evidence.render_execution import retain_source_pages


def reader_fixture(retained, monkeypatch):
    harness, writer = retained
    retain_source_pages(harness.binding, storage=harness.storage, service=writer)
    calls = []

    def read(doc, generation, access, **kwargs):
        assert (
            doc == harness.binding.document_id and generation == harness.binding.parse_generation_id
        )
        calls.append(kwargs)
        return writer.read_row(**kwargs)

    monkeypatch.setattr("lib.evidence.read_service.read_generation", read)
    access = DocumentAccessContext(household_id=uuid4(), user_id=uuid4(), household_role="owner")
    return harness, writer, GenerationEvidenceReader(harness.storage), access, calls


def test_historical_metadata_and_content_keep_exact_source_locators(retained, monkeypatch):
    harness, writer, reader, access, calls = reader_fixture(retained, monkeypatch)
    writer.row["run_status"] = "superseded"
    response = reader.manifest(
        harness.binding.document_id, harness.binding.parse_generation_id, access, offset=1, limit=1
    )
    assert response.total == 3 and response.pages[0].page_number == 2
    assert (
        response.processing_run_state == "superseded"
        and response.view_scope == "retained_parse_generation"
    )
    assert "isCurrent" not in response.model_dump(by_alias=True)
    assert response.parser_configuration == harness.registered.configuration
    page = reader.page(harness.binding.document_id, harness.binding.parse_generation_id, 2, access)
    assert page.page == harness.service.structure.pages[1]
    assert page.chunks == tuple(c for c in harness.service.structure.chunks if c.page_number == 2)
    assert calls == [{"offset": 1, "limit": 1}, {"offset": 1, "include_content": True}]
    text = page.model_dump_json(by_alias=True)
    assert "filesystem://" not in text and "raw_output" not in text


def test_metadata_is_registration_not_claim_of_bytes_availability(retained, monkeypatch):
    harness, writer, reader, access, _ = reader_fixture(retained, monkeypatch)
    harness.storage.path_for_uri(writer.assets[0].uri).unlink()
    response = reader.manifest(
        harness.binding.document_id, harness.binding.parse_generation_id, access
    )
    assert response.pages[0].render_registration == "registered"
    with pytest.raises(EvidenceUnavailable):
        reader.render(harness.binding.document_id, harness.binding.parse_generation_id, 1, access)


def test_acl_revoked_after_io_closes_spool_and_returns_no_bytes(retained, monkeypatch):
    harness, _, reader, access, _ = reader_fixture(retained, monkeypatch)
    from lib.evidence import read_service

    real_read = read_service.read_generation
    captured = []
    real_snapshot = read_service.snapshot_render

    def snapshot(*args):
        verified = real_snapshot(*args)
        captured.append(verified)

        def denied(*a, **k):
            raise EvidenceUnavailable("Retained generation is unavailable.")

        monkeypatch.setattr(read_service, "read_generation", denied)
        return verified

    monkeypatch.setattr(read_service, "snapshot_render", snapshot)
    with pytest.raises(EvidenceUnavailable):
        reader.render(harness.binding.document_id, harness.binding.parse_generation_id, 1, access)
    assert captured[0].stream.closed and real_read is not read_service.read_generation


def test_broken_checkpoint_fails_without_current_generation_fallback(retained, monkeypatch):
    harness, writer, reader, access, calls = reader_fixture(retained, monkeypatch)
    writer.checkpoints[0]["raw_output"] += " "
    with pytest.raises(EvidenceUnavailable):
        reader.page(harness.binding.document_id, harness.binding.parse_generation_id, 1, access)
    assert calls == [{"offset": 0, "include_content": True}]
    with pytest.raises(EvidenceUnavailable):
        reader.page(harness.binding.document_id, harness.binding.parse_generation_id, 4, access)
