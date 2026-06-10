from __future__ import annotations

from uuid import uuid4

from lib.config import get_settings
from lib.search import jobs as search_jobs


def test_enqueue_embed_document_job_skips_text_jobs_when_text_embeddings_disabled(
    monkeypatch,
) -> None:
    monkeypatch.setenv("STRUCTURA_EMBEDDING_TEXT_ENABLED", "false")
    get_settings.cache_clear()
    captured: dict[str, object] = {}

    def capture_job(_cur: object, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(search_jobs, "create_job_with_cursor", capture_job)
    try:
        job_id = search_jobs.enqueue_embed_document_job(
            object(),
            document_id=uuid4(),
            household_id=uuid4(),
        )
    finally:
        get_settings.cache_clear()

    assert job_id is None
    assert captured == {}


def test_enqueue_embed_document_job_enqueues_text_jobs_by_default(monkeypatch) -> None:
    get_settings.cache_clear()
    captured: dict[str, object] = {}

    def capture_job(_cur: object, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(search_jobs, "create_job_with_cursor", capture_job)
    try:
        job_id = search_jobs.enqueue_embed_document_job(
            object(),
            document_id=uuid4(),
            household_id=uuid4(),
        )
    finally:
        get_settings.cache_clear()

    assert job_id is not None
    assert captured["queue_name"] == "embeddings"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["modalities"] == ["text"]


def test_visual_embed_jobs_are_not_gated_by_the_text_embedding_flag(monkeypatch) -> None:
    monkeypatch.setenv("STRUCTURA_EMBEDDING_TEXT_ENABLED", "false")
    get_settings.cache_clear()
    captured: dict[str, object] = {}

    def capture_job(_cur: object, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(search_jobs, "create_job_with_cursor", capture_job)
    try:
        job_id = search_jobs.enqueue_visual_embed_document_job(
            object(),
            document_id=uuid4(),
            household_id=uuid4(),
        )
    finally:
        get_settings.cache_clear()

    assert job_id is not None
    assert captured["queue_name"] == "visual-embeddings"
