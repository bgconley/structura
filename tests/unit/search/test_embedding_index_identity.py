from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from lib.config import get_settings
from lib.contracts import SearchRequest
from lib.documents.access_policy import DocumentAccessContext
from lib.model_runtime.profiles import TEXT_EMBED_BLACKBIRD_PROFILE, VISUAL_EMBED_BLACKBIRD_PROFILE
from lib.search import repository
from lib.search.embedding_gateway import (
    DeterministicEmbeddingGateway,
    DeterministicVisualEmbeddingGateway,
    EmbeddedText,
    EmbeddingGatewayError,
    default_text_embedding_profile,
    default_visual_embedding_profile,
)
from lib.search.embedding_identity import fixture_input_identity
from lib.search.embedding_service import EmbeddingService
from lib.search.query import parse_search_request
from lib.search.service import SearchService


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("STRUCTURA_MODEL_MODE", "fixture")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_fixture_input_identity_includes_text_mime_bytes_purpose_and_profile():
    profile = default_visual_embedding_profile(2048)
    baseline = fixture_input_identity(
        "descriptor", profile, image_bytes=b"image", mime_type="image/png"
    )
    assert baseline.scheme == "fixture-input-v1"
    for change in (
        fixture_input_identity("changed", profile, image_bytes=b"image", mime_type="image/png"),
        fixture_input_identity("descriptor", profile, image_bytes=b"other", mime_type="image/png"),
        fixture_input_identity("descriptor", profile, image_bytes=b"image", mime_type="image/jpeg"),
        fixture_input_identity(
            "descriptor", profile, image_bytes=b"image", mime_type="image/png", purpose="query"
        ),
        fixture_input_identity(
            "descriptor",
            replace(profile, version="v2"),
            image_bytes=b"image",
            mime_type="image/png",
        ),
    ):
        assert change != baseline


def test_fixture_query_identity_is_distinct_without_changing_its_vector_space():
    profile = default_text_embedding_profile(32)
    document = DeterministicEmbeddingGateway(profile).embed_texts(["invoice total"])[0]
    query = DeterministicEmbeddingGateway(profile, purpose="query").embed_texts(["invoice total"])[
        0
    ]
    assert query.values == document.values
    assert query.profile == document.profile == profile
    assert query.input_identity is not None and query.input_identity.purpose == "query"
    assert query.input_identity != document.input_identity


def test_selected_v2_gateway_drives_actual_search_filter_profile(monkeypatch):
    monkeypatch.setenv("STRUCTURA_MODEL_MODE", "live")
    monkeypatch.setenv("STRUCTURA_TEXT_EMBED_PROFILE", TEXT_EMBED_BLACKBIRD_PROFILE)
    monkeypatch.setenv("STRUCTURA_VISUAL_EMBED_PROFILE", VISUAL_EMBED_BLACKBIRD_PROFILE)
    get_settings.cache_clear()
    service = SearchService()
    assert service.embedding_profile.name == "qwen3-embedding-4b-1536-blackbird"
    assert service.visual_embedding_profile.name == "qwen3-vl-embedding-2b-2048-blackbird"
    assert service.embedding_profile.version == service.visual_embedding_profile.version == "v2"
    captured = {}
    monkeypatch.setattr(
        service.embedding_gateway,
        "embed_texts",
        lambda texts: [
            EmbeddedText(
                text=texts[0], values=[1.0, *([0.0] * 1535)], profile=service.embedding_profile
            )
        ],
    )
    monkeypatch.setattr(
        repository, "semantic_search", lambda **kwargs: captured.update(kwargs) or []
    )
    service._semantic_candidates(
        parse_search_request(SearchRequest(query="invoice", mode="semantic")),
        DocumentAccessContext(uuid4(), uuid4(), "owner"),
    )
    assert (captured["profile_name"], captured["profile_version"], captured["dimensions"]) == (
        service.embedding_profile.name,
        "v2",
        1536,
    )


@pytest.mark.parametrize("visual", [False, True])
def test_explicit_fixture_profile_is_preserved_and_conflicting_gateway_is_rejected(visual):
    profile = default_visual_embedding_profile(32) if visual else default_text_embedding_profile(32)
    gateway = (
        DeterministicVisualEmbeddingGateway(profile)
        if visual
        else DeterministicEmbeddingGateway(profile)
    )
    params = (
        {"visual_embedding_profile": profile, "visual_embedding_gateway": gateway}
        if visual
        else {"embedding_profile": profile, "embedding_gateway": gateway}
    )
    service = SearchService(**params)
    assert (service.visual_embedding_profile if visual else service.embedding_profile) == profile
    params["visual_embedding_profile" if visual else "embedding_profile"] = replace(
        profile, version="other"
    )
    with pytest.raises(EmbeddingGatewayError, match="conflicts"):
        SearchService(**params)


def test_live_default_gateway_cannot_silently_ignore_a_supplied_profile(monkeypatch):
    monkeypatch.setenv("STRUCTURA_MODEL_MODE", "live")
    monkeypatch.setenv("STRUCTURA_TEXT_EMBED_PROFILE", TEXT_EMBED_BLACKBIRD_PROFILE)
    get_settings.cache_clear()
    with pytest.raises(EmbeddingGatewayError, match="conflicts"):
        SearchService(embedding_profile=default_text_embedding_profile(1536))
    with pytest.raises(EmbeddingGatewayError, match="conflicts"):
        EmbeddingService(profile=default_text_embedding_profile(1536))


def test_gateway_result_profile_cannot_drift_before_database_query(monkeypatch):
    service = SearchService()
    calls = []
    monkeypatch.setattr(
        service.embedding_gateway,
        "embed_texts",
        lambda texts: [
            EmbeddedText(
                text=texts[0],
                values=[1.0],
                profile=replace(service.embedding_profile, version="other"),
            )
        ],
    )
    monkeypatch.setattr(repository, "semantic_search", lambda **kwargs: calls.append(kwargs) or [])
    with pytest.raises(EmbeddingGatewayError, match="conflicts"):
        service._semantic_candidates(
            parse_search_request(SearchRequest(query="invoice", mode="semantic")),
            DocumentAccessContext(uuid4(), uuid4(), "owner"),
        )
    assert calls == []
