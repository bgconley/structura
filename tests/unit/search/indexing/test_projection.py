from __future__ import annotations

from dataclasses import asdict
from uuid import uuid4

import pytest
from pydantic import ValidationError

from lib.document_parsing.structure import DocumentStructure
from lib.model_runtime.contracts import EmbeddingInput, EmbeddingRequest
from lib.model_runtime.embedding_identity import embedding_input_hashes
from lib.model_runtime.profiles import get_model_profile
from lib.search.indexing.configuration import IndexConfiguration, index_configuration
from lib.search.indexing.errors import IndexCandidateError
from lib.search.indexing.projection import project_inputs
from tests.unit.search.indexing.conftest import assets_for


def test_complete_text_preserves_exact_sources_and_shared_identity(candidate, structure):
    config, manifest = candidate
    assert len(manifest.inputs) == len(structure.chunks) > 0
    for item, chunk in zip(manifest.inputs, structure.chunks, strict=True):
        assert (item.owner_id, item.text, item.element_ids, item.text_origins) == (
            chunk.id,
            chunk.text,
            chunk.element_ids,
            chunk.text_origins,
        )
        request = EmbeddingRequest(
            profile_name=config.spaces[0].profile,
            inputs=(EmbeddingInput(text=item.text),),
            output_dimensions=1536,
            timeout_seconds=30,
        )
        assert (
            item.model_input_sha256
            == embedding_input_hashes(request, get_model_profile(request.profile_name))[0]
        )
    assert len(manifest.pages) == len(structure.pages)
    assert all(page.visual == "not_requested" for page in manifest.pages)
    assert config.fact_basis == config.metadata_basis == "not_collected"


def test_model_configuration_freezes_actual_protocol_and_rejects_substitution():
    config = index_configuration(model_mode="live")
    assert tuple(s.dimensions for s in config.spaces) == (1536, 2048)
    for space in config.spaces:
        assert space.protocol.identity_policy == "reported_model"
        assert asdict(space.protocol) == asdict(get_model_profile(space.profile).embedding_protocol)
    for field, value in (("dimensions", 1024), ("profile", "other:v2")):
        payload = config.model_dump(mode="json")
        payload["spaces"][0][field] = value
        with pytest.raises(ValidationError):
            IndexConfiguration.model_validate(payload)
    payload = config.model_dump(mode="json")
    payload["spaces"][0]["protocol"]["artifact_revision"] = "other"
    with pytest.raises(ValidationError):
        IndexConfiguration.model_validate(payload)


def test_visual_input_set_requires_every_eligible_original_render(structure):
    identity = uuid4()
    config = index_configuration(model_mode="fixture", modalities=("visual",))
    assets = assets_for(structure, identity)
    manifest = project_inputs(structure, index_id=identity, configuration=config, assets=assets)
    assert len(manifest.inputs) == len(structure.pages) == len(manifest.pages)
    assert all(
        p.visual == "eligible" and "image_original" in p.visual_reasons for p in manifest.pages
    )
    with pytest.raises(IndexCandidateError, match="render"):
        project_inputs(structure, index_id=identity, configuration=config, assets=assets[:-1])
    with pytest.raises(IndexCandidateError, match="identity"):
        project_inputs(structure, index_id=uuid4(), configuration=config, assets=assets)
    bad = (
        assets[0].model_copy(
            update={"source": assets[0].source.model_copy(update={"image_sha256": "f" * 64})}
        ),
        *assets[1:],
    )
    with pytest.raises(IndexCandidateError, match="render"):
        project_inputs(structure, index_id=identity, configuration=config, assets=bad)


def test_zero_visual_eligibility_is_explicit_and_does_not_erase_pages(structure):
    payload = structure.model_dump(mode="json")
    payload["source"]["mime_type"] = "application/pdf"
    for page in payload["pages"]:
        page["source"]["native_text"] = (
            "This digital page has sufficient native text for text retrieval."
        )
        page["source"]["native_text_origin"] = "pdf_native"
    changed = DocumentStructure.model_validate(payload)
    result = project_inputs(
        changed,
        index_id=uuid4(),
        configuration=index_configuration(model_mode="fixture", modalities=("visual",)),
    )
    assert result.inputs == ()
    assert len(result.pages) == len(structure.pages)
    assert all(
        p.visual == "ineligible" and p.visual_reasons == ("digital_text_page",)
        for p in result.pages
    )


def test_overflow_and_deferred_source_cannot_look_complete(structure):
    config = index_configuration(model_mode="fixture", modalities=("text",))
    for update in ({"max_text_bytes": 1}, {"max_inputs": 1}):
        with pytest.raises(IndexCandidateError, match="budget"):
            project_inputs(
                structure, index_id=uuid4(), configuration=config.model_copy(update=update)
            )
    page = structure.pages[0].model_copy(update={"state": "deferred"})
    incomplete = structure.model_copy(update={"pages": (page, *structure.pages[1:])})
    with pytest.raises(IndexCandidateError, match="complete"):
        project_inputs(incomplete, index_id=uuid4(), configuration=config)


def test_visual_identity_binds_actual_image_hash_and_mime(structure):
    identity = uuid4()
    config = index_configuration(model_mode="fixture", modalities=("visual",))
    assets = assets_for(structure, identity)
    manifest = project_inputs(structure, index_id=identity, configuration=config, assets=assets)
    item = manifest.inputs[0]
    assert item.text == "" and item.render_asset_id == assets[0].id
    assert item.content_sha256 != item.model_input_sha256
    assert item.identity_scheme == "model-input-v1" and item.purpose == "document"


def test_whitespace_chunks_have_explicit_disposition_instead_of_empty_model_call(structure):
    changed = structure.model_copy(
        update={"chunks": tuple(c.model_copy(update={"text": " \n\t"}) for c in structure.chunks)}
    )
    manifest = project_inputs(
        changed,
        index_id=uuid4(),
        configuration=index_configuration(model_mode="fixture", modalities=("text",)),
    )
    assert manifest.inputs == ()
    assert {identity for page in manifest.pages for identity in page.whitespace_chunk_ids} == {
        c.id for c in structure.chunks
    }
    assert all(page.text == "ineligible" for page in manifest.pages)
