"""Short fenced render-write transactions; media verification remains outside them."""

from __future__ import annotations

from typing import Any

from lib.db.connection import db_connection
from lib.document_processing.models import ProcessingBinding
from lib.evidence import write_repository
from lib.evidence.authority_repository import fence_set, lock_set
from lib.evidence.blob_commit import prepare_render_commit
from lib.evidence.manifest import completion_manifest
from lib.evidence.media import snapshot_render
from lib.evidence.models import RenderSetBinding, RenderSetSnapshot, RetainedPageAsset
from lib.storage import ObjectStorage


class RetainedEvidenceWriter:
    def __init__(self, storage: ObjectStorage | None = None):
        self.storage = storage or ObjectStorage()

    def start(self, processing: ProcessingBinding) -> RenderSetBinding:
        with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout='5s'")
            binding = write_repository.create_set(cur, processing)
            conn.commit()
            return binding

    def snapshot(self, binding: RenderSetBinding) -> RenderSetSnapshot:
        with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
            header, expected = lock_set(cur, binding)
            assets = write_repository.load_assets(cur, binding, expected)
            fence_set(cur, binding)
            return RenderSetSnapshot(expected, assets, header["state"], header["completion_sha256"])

    def execution_source(self, binding: RenderSetBinding) -> dict[str, Any]:
        with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
            return write_repository.execution_source(cur, binding)

    def assert_authority(self, binding: RenderSetBinding) -> None:
        with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='5s'")
            cur.execute("SET LOCAL lock_timeout='2s'")
            lock_set(cur, binding)
            fence_set(cur, binding)

    def checkpoint(self, binding: RenderSetBinding, asset: RetainedPageAsset) -> str:
        # Verified staging occurs before SQL. Only the final atomic blob commit
        # (or bounded verification of an existing blob) holds the content lock.
        with prepare_render_commit(asset, self.storage) as prepared:
            with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
                digest = write_repository.register_asset(
                    cur,
                    binding,
                    asset,
                    commit_source=prepared.commit_under_content_lock,
                )
                conn.commit()
        snapshot_render(asset, self.storage).close()
        return digest

    def seal(self, binding: RenderSetBinding) -> dict[str, Any]:
        snapshot = self.snapshot(binding)
        # Require the entire immutable page inventory before byte verification.
        # A concurrent final-page insert cannot silently expand the verified set.
        completion_manifest(snapshot.expected, snapshot.assets)
        for asset in snapshot.assets:
            snapshot_render(asset, self.storage).close()
        with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
            result = write_repository.seal_set(cur, binding)
            conn.commit()
            return result
