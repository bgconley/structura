"""Stage verified bytes outside SQL; establish the exact object under its hash lock."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from lib.evidence.errors import EvidenceConflict
from lib.evidence.media import snapshot_render
from lib.evidence.models import MAX_RENDER_BYTES, RetainedPageAsset
from lib.storage import ObjectStorage, cleanup_unreferenced_stored_object
from lib.storage.service import StagedObject, StoredObject, object_uri, parse_object_uri


@dataclass
class PreparedRenderCommit:
    storage: ObjectStorage
    asset: RetainedPageAsset
    staged: StagedObject
    role: str
    committed: StoredObject | None = None

    def commit_under_content_lock(self) -> None:
        """Caller holds the exact content hash until the page transaction ends.

        Rendering, PNG decoding and staging are already complete. Only atomic
        object commit or bounded existing-object verification occurs under SQL
        locks, preventing reference cleanup from deleting bytes before INSERT.
        """
        self.committed = self.storage.commit_staged(self.staged, kind="derived", role=self.role)
        if (
            self.committed.uri != self.asset.uri
            or self.committed.sha256 != self.asset.render.image_sha256
            or self.committed.byte_size != self.asset.byte_size
        ):
            raise EvidenceConflict("Committed render differs from its exact retained source.")


@contextmanager
def prepare_render_commit(
    asset: RetainedPageAsset, storage: ObjectStorage
) -> Iterator[PreparedRenderCommit]:
    address = parse_object_uri(asset.uri)
    if (
        address.kind != "derived"
        or not address.filename.endswith(".blob")
        or not address.filename[:-5]
        or object_uri(kind="derived", sha256=asset.render.image_sha256, filename=address.filename)
        != asset.uri
    ):
        raise EvidenceConflict("Retained source URI is not an exact derived object identity.")
    verified = snapshot_render(asset, storage)
    try:
        staged = storage.stage_stream(verified.stream, kind="derived", max_bytes=MAX_RENDER_BYTES)
    finally:
        verified.close()
    prepared = PreparedRenderCommit(storage, asset, staged, address.filename[:-5])
    try:
        if staged.sha256 != asset.render.image_sha256 or staged.byte_size != asset.byte_size:
            raise EvidenceConflict("Staged render differs from its verified source.")
        yield prepared
    except BaseException:
        # The service's nested transaction has closed and rolled back before
        # control reaches here. Honor the callback's actual created flag; it may
        # have recreated an object the original caller had merely reused.
        cleanup_unreferenced_stored_object(prepared.committed)
        raise
    finally:
        storage.cleanup_staged(staged)
