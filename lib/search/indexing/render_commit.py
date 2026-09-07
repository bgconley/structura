"""Establish verified candidate render bytes under their publication content locks."""

from __future__ import annotations

import io
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from lib.search.indexing.errors import IndexCandidateError
from lib.search.indexing.models import IndexRenderAsset
from lib.search.indexing.render_verification import read_verified_render, validate_render_inventory
from lib.storage import ObjectStorage, cleanup_unreferenced_stored_object
from lib.storage.service import StagedObject, StoredObject, object_uri, parse_object_uri


@dataclass
class PreparedIndexRenders:
    storage: ObjectStorage
    staged: list[tuple[IndexRenderAsset, StagedObject, str]] = field(default_factory=list)
    committed: list[StoredObject] = field(default_factory=list)

    def commit_under_content_locks(self) -> None:
        """Only final atomic commits/bounded existing-object checks hold SQL locks."""
        for asset, staged, role in self.staged:
            stored = self.storage.commit_staged(staged, kind="derived", role=role)
            # Record the actual recreation flag before any later callback/fence fails.
            self.committed.append(stored)
            if (stored.uri, stored.sha256, stored.byte_size) != (
                asset.uri,
                asset.source.image_sha256,
                asset.byte_size,
            ):
                raise IndexCandidateError(
                    "Committed candidate render differs from its frozen source."
                )


@contextmanager
def prepare_render_commits(
    assets: tuple[IndexRenderAsset, ...],
    storage: ObjectStorage,
) -> Iterator[PreparedIndexRenders]:
    validate_render_inventory(assets)
    prepared = PreparedIndexRenders(storage)
    try:
        # At most500 immutable page descriptors; each verified PNG is <=10MiB.
        # Only one page's bytes are in memory. Staging is entirely outside SQL.
        for asset in assets:
            address = parse_object_uri(asset.uri)
            if (
                address.kind != "derived"
                or not address.filename.endswith(".blob")
                or not address.filename[:-5]
                or object_uri(
                    kind="derived", sha256=asset.source.image_sha256, filename=address.filename
                )
                != asset.uri
            ):
                raise IndexCandidateError(
                    "Candidate render URI is not an exact derived object identity."
                )
            with io.BytesIO(read_verified_render(asset, storage)) as source:
                staged = storage.stage_stream(source, kind="derived", max_bytes=10 * 1024 * 1024)
            prepared.staged.append((asset, staged, address.filename[:-5]))
            if staged.sha256 != asset.source.image_sha256 or staged.byte_size != asset.byte_size:
                raise IndexCandidateError(
                    "Staged candidate render differs from its verified source."
                )
        yield prepared
    except BaseException:
        # The service nests SQL inside this context; rollback precedes cleanup.
        # A callback may recreate an originally reused object after cleanup wins.
        for stored in prepared.committed:
            cleanup_unreferenced_stored_object(stored)
        raise
    finally:
        for _, staged, _ in prepared.staged:
            storage.cleanup_staged(staged)
