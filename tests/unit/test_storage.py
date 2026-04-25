from __future__ import annotations

from io import BytesIO

import pytest

from lib.storage import InvalidObjectUri, ObjectStorage, StorageError, object_uri, parse_object_uri


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
