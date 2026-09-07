from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

import pytest

from lib.document_processing.source_repository import load_processing_source


def test_source_read_is_fenced_and_transaction_closes_before_return(execution, monkeypatch):
    harness = execution()
    source = harness.registered
    events = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            pass

        def execute(self, query, params=None):
            if "FROM document_assets" in query:
                events.append("asset-lock")
                assert "FOR KEY SHARE" in query
                assert params == (
                    source.original_asset_id,
                    harness.binding.document_id,
                    source.original_sha256,
                )
                assert "canonical_asset_id" not in query and "is_current" not in query

        def fetchone(self):
            return {
                "id": source.original_asset_id,
                "sha256": source.original_sha256,
                "uri": source.uri,
                "mime_type": source.mime_type,
                "byte_size": source.byte_size,
            }

    class Connection:
        def cursor(self):
            return Cursor()

    @contextmanager
    def connection(**kwargs):
        events.append("transaction-open")
        try:
            yield Connection()
        finally:
            events.append("transaction-closed")

    def lock(cur, binding):
        assert binding == harness.binding
        events.append("run-lock")
        return {
            "original_asset_id": source.original_asset_id,
            "original_sha256": source.original_sha256,
            "config_json": source.configuration.model_dump(mode="json"),
            "config_sha256": source.configuration.fingerprint,
        }

    monkeypatch.setattr("lib.document_processing.source_repository.db_connection", connection)
    monkeypatch.setattr("lib.document_processing.source_repository.lock_current_run", lock)
    monkeypatch.setattr(
        "lib.document_processing.source_repository.fence_processing_attempt",
        lambda cur, binding: events.append("attempt-fence"),
    )
    assert load_processing_source(harness.binding) == source
    assert events == [
        "transaction-open",
        "run-lock",
        "asset-lock",
        "attempt-fence",
        "transaction-closed",
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("byte_size", "12"),
        ("byte_size", 0),
        ("byte_size", True),
        ("mime_type", "text/html"),
        ("original_asset_id", str(uuid4())),
    ],
)
def test_registered_source_does_not_coerce_invalid_metadata(execution, field, value):
    from pydantic import ValidationError

    from lib.document_processing.source_repository import RegisteredParseSource

    data = execution().registered.model_dump()
    with pytest.raises(ValidationError):
        RegisteredParseSource.model_validate({**data, field: value})
