import pytest

from lib.config import get_settings

from ..test_human_confirmed_promotion import promotion_document as promotion_document


@pytest.fixture(autouse=True)
def enabled_embedding_queue(monkeypatch):
    # These tests require a real enqueue in the transaction, independent of the
    # operator's optional text-embedding setting. They never run a worker/model.
    monkeypatch.setenv("STRUCTURA_EMBEDDING_TEXT_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
