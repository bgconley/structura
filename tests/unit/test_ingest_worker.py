from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from uuid import uuid4

import pytest

from workers.ingest import worker


def test_acknowledge_ingest_uses_original_asset_after_canonical_asset_moves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = uuid4()
    original_asset_id = uuid4()
    derived_asset_id = uuid4()
    original_sha256 = "a" * 64
    derived_sha256 = "b" * 64

    fake_db = _FakeIngestDatabase(
        document_id=document_id,
        canonical_asset_id=derived_asset_id,
        assets=[
            {
                "id": original_asset_id,
                "document_id": document_id,
                "asset_role": "original",
                "sha256": original_sha256,
                "byte_size": 651,
                "created_at": 1,
            },
            {
                "id": derived_asset_id,
                "document_id": document_id,
                "asset_role": "docling_json",
                "sha256": derived_sha256,
                "byte_size": 1031,
                "created_at": 2,
            },
        ],
    )
    monkeypatch.setattr(worker, "db_connection", fake_db.connection)

    summary = worker._acknowledge_ingested_document(document_id)

    assert summary == {
        "document_id": document_id,
        "asset_id": original_asset_id,
        "sha256": original_sha256,
        "byte_size": 651,
    }


class _FakeIngestDatabase:
    def __init__(
        self,
        *,
        document_id: object,
        canonical_asset_id: object,
        assets: list[dict[str, object]],
    ) -> None:
        self.document_id = document_id
        self.canonical_asset_id = canonical_asset_id
        self.assets = assets

    @contextmanager
    def connection(self) -> Any:
        yield _FakeConnection(self)


class _FakeConnection:
    def __init__(self, database: _FakeIngestDatabase) -> None:
        self.database = database

    @contextmanager
    def cursor(self) -> Any:
        yield _FakeCursor(self.database)


class _FakeCursor:
    def __init__(self, database: _FakeIngestDatabase) -> None:
        self.database = database
        self._document_id: object | None = None
        self._query = ""

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self._query = query
        self._document_id = params[0]

    def fetchone(self) -> dict[str, object] | None:
        if self._document_id != self.database.document_id:
            return None
        if "a.id = d.canonical_asset_id" in self._query:
            original_assets = [
                asset
                for asset in self.database.assets
                if asset["id"] == self.database.canonical_asset_id
                and asset["asset_role"] == "original"
            ]
        else:
            original_assets = [
                asset
                for asset in self.database.assets
                if asset["document_id"] == self._document_id and asset["asset_role"] == "original"
            ]
        if not original_assets:
            return None
        asset = sorted(original_assets, key=lambda item: int(item["created_at"]))[0]
        return {
            "document_id": self.database.document_id,
            "asset_id": asset["id"],
            "sha256": asset["sha256"],
            "byte_size": asset["byte_size"],
        }
