from __future__ import annotations

from io import BytesIO
from types import ModuleType

import pytest

from lib.documents import canonical_parse
from lib.extraction import extraction_repository
from lib.storage import (
    InvalidObjectUri,
    ObjectStorage,
    StorageError,
    StoredObject,
    object_uri,
    parse_object_uri,
)
from workers.previews import service as preview_service


def test_content_addressed_write_dedupe_and_verify(tmp_path) -> None:
    storage = ObjectStorage(
        canonical_root=tmp_path / "canonical",
        derived_root=tmp_path / "derived",
        export_root=tmp_path / "exports",
    )

    staged = storage.stage_stream(BytesIO(b"original bytes"), kind="canonical")
    stored = storage.commit_staged(staged, kind="canonical", role="original")
    duplicate = storage.commit_staged(
        storage.stage_stream(BytesIO(b"original bytes"), kind="canonical"),
        kind="canonical",
        role="original",
    )

    assert stored.uri == duplicate.uri
    assert stored.path.exists()
    assert storage.verify(
        uri=stored.uri,
        expected_sha256=stored.sha256,
        expected_size=stored.byte_size,
    ).ok


def test_object_uri_rejects_path_traversal() -> None:
    with pytest.raises(InvalidObjectUri):
        parse_object_uri("filesystem://canonical/sha256/aa/bb/" + ("a" * 64) + "/../evil")
    with pytest.raises(InvalidObjectUri):
        object_uri(kind="canonical", sha256="a" * 64, filename="../evil")


def test_missing_file_detection(tmp_path) -> None:
    storage = ObjectStorage(
        canonical_root=tmp_path / "canonical",
        derived_root=tmp_path / "derived",
        export_root=tmp_path / "exports",
    )
    uri = object_uri(kind="canonical", sha256="a" * 64, filename="original.blob")

    consistency = storage.verify(uri=uri, expected_sha256="a" * 64, expected_size=10)

    assert not consistency.exists
    assert not consistency.ok


def test_immutable_existing_object_mismatch_is_rejected(tmp_path) -> None:
    storage = ObjectStorage(
        canonical_root=tmp_path / "canonical",
        derived_root=tmp_path / "derived",
        export_root=tmp_path / "exports",
    )
    staged = storage.stage_stream(BytesIO(b"first"), kind="canonical")
    stored = storage.commit_staged(staged, kind="canonical", role="original")
    stored.path.write_bytes(b"tampered")

    with pytest.raises(StorageError):
        storage.commit_staged(
            storage.stage_stream(BytesIO(b"first"), kind="canonical"),
            kind="canonical",
            role="original",
        )


@pytest.mark.parametrize(
    ("module", "cleanup_name"),
    [
        (canonical_parse, "_cleanup_created_objects"),
        (extraction_repository, "_cleanup_created"),
        (preview_service, "_cleanup_created_objects"),
    ],
)
def test_rollback_cleanup_delegates_to_reference_safe_cleanup(
    module: ModuleType,
    cleanup_name: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    path = tmp_path / f"{module.__name__.replace('.', '-')}.blob"
    path.write_bytes(b"referenced derived bytes")
    stored = StoredObject(
        uri=object_uri(
            kind="derived",
            sha256="a" * 64,
            filename=f"{module.__name__.replace('.', '-')}.blob",
        ),
        sha256="a" * 64,
        byte_size=path.stat().st_size,
        path=path,
        created=True,
    )
    cleaned: list[StoredObject] = []

    def fake_cleanup(value: StoredObject | None) -> None:
        if value is not None:
            cleaned.append(value)

    monkeypatch.setattr(module, "cleanup_unreferenced_stored_object", fake_cleanup, raising=False)

    getattr(module, cleanup_name)([stored])

    assert cleaned == [stored]
    assert path.exists()
