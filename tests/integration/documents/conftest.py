import os

import pytest

from lib.config import get_settings
from tests.integration.documents.browse_support import BrowseCorpus, create_identity, login


@pytest.fixture
def browse_corpus(monkeypatch, tmp_path):
    database_url = os.environ.get("STRUCTURA_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Isolated test database required")
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", database_url)
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    monkeypatch.setenv("STRUCTURA_MODEL_MODE", "fixture")
    monkeypatch.setenv("STRUCTURA_RUNTIME_ROOT", str(tmp_path / "runtime"))
    get_settings.cache_clear()
    owner = create_identity("owner")
    yield BrowseCorpus(owner, login(owner))
    get_settings.cache_clear()
