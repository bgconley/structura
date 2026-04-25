from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal
from urllib.parse import urlparse

from lib.config import Settings, get_settings

StorageKind = Literal["canonical", "derived", "exports"]

HASH_RE = re.compile(r"^[a-f0-9]{64}$")
SAFE_OBJECT_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class StorageError(Exception):
    pass


class InvalidObjectUri(StorageError):
    pass


class UploadTooLarge(StorageError):
    pass


@dataclass(frozen=True)
class StoredObject:
    uri: str
    sha256: str
    byte_size: int
    path: Path
    created: bool = False


@dataclass(frozen=True)
class StagedObject:
    temp_path: Path
    sha256: str
    byte_size: int


@dataclass(frozen=True)
class ObjectConsistency:
    exists: bool
    size_matches: bool
    hash_matches: bool
    actual_size: int | None = None
    actual_sha256: str | None = None

    @property
    def ok(self) -> bool:
        return self.exists and self.size_matches and self.hash_matches


def object_filename_for_role(role: str) -> str:
    if not SAFE_OBJECT_NAME_RE.fullmatch(role):
        raise StorageError("Object role must be a safe path segment.")
    return f"{role}.blob"


def object_uri(*, kind: StorageKind, sha256: str, filename: str) -> str:
    normalized_hash = sha256.lower()
    if not HASH_RE.fullmatch(normalized_hash):
        raise InvalidObjectUri("Object hash must be a 64-character lowercase SHA-256 digest.")
    if "/" in filename or "\\" in filename or not SAFE_OBJECT_NAME_RE.fullmatch(filename):
        raise InvalidObjectUri("Object filename must be a safe single path segment.")
    return (
        f"filesystem://{kind}/sha256/{normalized_hash[:2]}/{normalized_hash[2:4]}/"
        f"{normalized_hash}/{filename}"
    )


@dataclass(frozen=True)
class ParsedObjectUri:
    kind: StorageKind
    sha256: str
    filename: str


def parse_object_uri(uri: str) -> ParsedObjectUri:
    parsed = urlparse(uri)
    if parsed.scheme != "filesystem":
        raise InvalidObjectUri("Unsupported object URI scheme.")
    if parsed.netloc not in {"canonical", "derived", "exports"}:
        raise InvalidObjectUri("Unsupported object URI storage kind.")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 5 or parts[0] != "sha256":
        raise InvalidObjectUri("Malformed content-addressed object URI.")
    prefix_a, prefix_b, sha256, filename = parts[1], parts[2], parts[3], parts[4]
    if prefix_a != sha256[:2] or prefix_b != sha256[2:4] or not HASH_RE.fullmatch(sha256):
        raise InvalidObjectUri("Object URI hash prefixes do not match the digest.")
    if "/" in filename or "\\" in filename or not SAFE_OBJECT_NAME_RE.fullmatch(filename):
        raise InvalidObjectUri("Object URI filename is unsafe.")
    return ParsedObjectUri(kind=parsed.netloc, sha256=sha256, filename=filename)  # type: ignore[arg-type]


class ObjectStorage:
    def __init__(
        self,
        *,
        canonical_root: Path | None = None,
        derived_root: Path | None = None,
        export_root: Path | None = None,
        settings: Settings | None = None,
    ) -> None:
        resolved_settings = settings or get_settings()
        self.roots: dict[StorageKind, Path] = {
            "canonical": canonical_root or resolved_settings.canonical_objects_root,
            "derived": derived_root or resolved_settings.derived_objects_root,
            "exports": export_root or resolved_settings.export_objects_root,
        }

    def root_for(self, kind: StorageKind) -> Path:
        root = self.roots[kind].resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def stage_stream(
        self,
        stream: BinaryIO,
        *,
        kind: StorageKind = "canonical",
        max_bytes: int | None = None,
        chunk_size: int = 1024 * 1024,
    ) -> StagedObject:
        root = self.root_for(kind)
        tmp_dir = root / ".tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        total = 0
        fd, temp_name = tempfile.mkstemp(prefix="structura-", suffix=".upload", dir=tmp_dir)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as target:
                while True:
                    chunk = stream.read(chunk_size)
                    if not chunk:
                        break
                    total += len(chunk)
                    if max_bytes is not None and total > max_bytes:
                        raise UploadTooLarge(f"Upload exceeds {max_bytes} bytes.")
                    digest.update(chunk)
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        return StagedObject(temp_path=temp_path, sha256=digest.hexdigest(), byte_size=total)

    def commit_staged(
        self,
        staged: StagedObject,
        *,
        kind: StorageKind,
        role: str,
    ) -> StoredObject:
        filename = object_filename_for_role(role)
        uri = object_uri(kind=kind, sha256=staged.sha256, filename=filename)
        destination = self.path_for_uri(uri)
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.exists():
            self._assert_existing_matches(destination, staged.sha256, staged.byte_size)
            staged.temp_path.unlink(missing_ok=True)
            return StoredObject(
                uri=uri,
                sha256=staged.sha256,
                byte_size=staged.byte_size,
                path=destination,
                created=False,
            )

        os.replace(staged.temp_path, destination)
        return StoredObject(
            uri=uri,
            sha256=staged.sha256,
            byte_size=staged.byte_size,
            path=destination,
            created=True,
        )

    def store_bytes(self, data: bytes, *, kind: StorageKind, role: str) -> StoredObject:
        digest = hashlib.sha256(data).hexdigest()
        filename = object_filename_for_role(role)
        uri = object_uri(kind=kind, sha256=digest, filename=filename)
        destination = self.path_for_uri(uri)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            self._assert_existing_matches(destination, digest, len(data))
            return StoredObject(
                uri=uri,
                sha256=digest,
                byte_size=len(data),
                path=destination,
                created=False,
            )

        tmp_dir = self.root_for(kind) / ".tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix="structura-", suffix=".derived", dir=tmp_dir)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as target:
                target.write(data)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temp_path, destination)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        return StoredObject(
            uri=uri,
            sha256=digest,
            byte_size=len(data),
            path=destination,
            created=True,
        )

    def path_for_uri(self, uri: str) -> Path:
        parsed = parse_object_uri(uri)
        root = self.root_for(parsed.kind)
        path = (
            root
            / "sha256"
            / parsed.sha256[:2]
            / parsed.sha256[2:4]
            / parsed.sha256
            / parsed.filename
        )
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            raise InvalidObjectUri("Object URI resolves outside the configured storage root.")
        return resolved

    def verify(
        self,
        *,
        uri: str,
        expected_sha256: str | None,
        expected_size: int | None,
    ) -> ObjectConsistency:
        path = self.path_for_uri(uri)
        if not path.exists() or not path.is_file():
            return ObjectConsistency(exists=False, size_matches=False, hash_matches=False)
        actual_size = path.stat().st_size
        actual_hash = file_sha256(path)
        return ObjectConsistency(
            exists=True,
            size_matches=expected_size is None or actual_size == expected_size,
            hash_matches=expected_sha256 is None or actual_hash == expected_sha256.lower(),
            actual_size=actual_size,
            actual_sha256=actual_hash,
        )

    def cleanup_staged(self, staged: StagedObject | None) -> None:
        if staged:
            staged.temp_path.unlink(missing_ok=True)

    def _assert_existing_matches(self, path: Path, sha256: str, byte_size: int) -> None:
        if path.stat().st_size != byte_size or file_sha256(path) != sha256:
            raise StorageError("Existing content-addressed object does not match expected bytes.")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def remove_empty_hash_dir(path: Path) -> None:
    for candidate in (path.parent, path.parent.parent, path.parent.parent.parent):
        try:
            candidate.rmdir()
        except OSError:
            break


def copy_to_stream(path: Path, target: BinaryIO) -> None:
    with path.open("rb") as source:
        shutil.copyfileobj(source, target)
