"""Candidate-only transaction boundary; model execution and activation are separate."""

from __future__ import annotations

from uuid import UUID

from lib.db.connection import db_connection
from lib.document_processing.models import ProcessingBinding
from lib.search.indexing import (
    header_repository,
    input_repository,
    snapshot_repository,
    vector_repository,
)
from lib.search.indexing.authority_repository import fence_index, lock_checkpoint_index
from lib.search.indexing.configuration import IndexConfiguration
from lib.search.indexing.errors import IndexCheckpointConflict
from lib.search.indexing.models import (
    IndexBinding,
    IndexInput,
    IndexManifest,
    IndexPreparationSource,
    IndexRenderAsset,
    PreparedIndexSnapshot,
    VectorObservation,
)
from lib.search.indexing.render_commit import prepare_render_commits
from lib.search.indexing.render_verification import read_verified_render, validate_render_inventory
from lib.storage import ObjectStorage


class CandidateIndexService:
    def __init__(self, storage: ObjectStorage | None = None):
        self.storage = storage or ObjectStorage()

    def start(
        self,
        processing: ProcessingBinding,
        *,
        request_key: UUID,
        configuration: IndexConfiguration,
    ) -> IndexBinding:
        with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = '5s'")
            binding = header_repository.start_index(
                cur, processing, request_key=request_key, configuration=configuration
            )
            conn.commit()
            return binding

    def prepare(
        self, binding: IndexBinding, assets: tuple[IndexRenderAsset, ...] = ()
    ) -> IndexManifest:
        validate_render_inventory(assets)
        self.assert_authority(binding)
        # Verified staging is bounded and occurs outside SQL, one page at a time.
        with prepare_render_commits(assets, self.storage) as prepared:
            with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
                manifest = input_repository.prepare_inputs(
                    cur,
                    binding,
                    assets,
                    commit_sources=prepared.commit_under_content_locks,
                )
                conn.commit()
        # The content lock now establishes bytes before references commit. This
        # postcheck additionally reports external storage corruption, never success.
        for asset in assets:
            read_verified_render(asset, self.storage)
        return manifest

    def load_preparation(self, binding: IndexBinding) -> IndexPreparationSource:
        with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
            return snapshot_repository.load_preparation(cur, binding)

    def load_prepared(self, binding: IndexBinding) -> PreparedIndexSnapshot:
        with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
            return snapshot_repository.load_prepared(cur, binding)

    def missing_inputs(self, binding: IndexBinding) -> tuple[IndexInput, ...]:
        with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
            return vector_repository.list_missing_inputs(cur, binding)

    def checkpoint(self, binding: IndexBinding, observation: VectorObservation) -> str:
        # Revalidate exact bytes before publication as well as future invocation;
        # historical descriptor registration alone does not prove present storage.
        asset = self._input_asset(binding, observation.input_id)
        if asset is not None:
            read_verified_render(asset, self.storage)
        with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
            digest = vector_repository.persist_vector(cur, binding, observation)
            conn.commit()
            return digest

    def seal(self, binding: IndexBinding) -> dict[str, object]:
        for asset in self._registered_assets(binding):
            read_verified_render(asset, self.storage)
        with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
            completion = vector_repository.seal_index(cur, binding)
            conn.commit()
            return completion

    def cancel(self, binding: IndexBinding) -> None:
        with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
            header_repository.cancel_index(cur, binding)
            conn.commit()

    def assert_authority(self, binding: IndexBinding) -> None:
        with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '5s'")
            cur.execute("SET LOCAL lock_timeout = '2s'")
            lock_checkpoint_index(cur, binding)
            fence_index(cur, binding)

    def _registered_assets(self, binding: IndexBinding) -> tuple[IndexRenderAsset, ...]:
        """Snapshot immutable render references; reads happen after this TX closes."""
        with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
            lock_checkpoint_index(cur, binding)
            cur.execute(
                "SELECT asset_json FROM document_generation_render_assets "
                "WHERE index_generation_id=%s ORDER BY page_number",
                (binding.index_generation_id,),
            )
            assets = tuple(
                IndexRenderAsset.model_validate(row["asset_json"]) for row in cur.fetchall()
            )
            fence_index(cur, binding)
            return assets

    def _input_asset(self, binding: IndexBinding, input_id: UUID) -> IndexRenderAsset | None:
        with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
            header = lock_checkpoint_index(cur, binding)
            item = input_repository.load_input(cur, binding, header, input_id)
            asset = None
            if item.render_asset_id is not None:
                cur.execute(
                    "SELECT asset_json FROM document_generation_render_assets WHERE id=%s "
                    "AND index_generation_id=%s",
                    (item.render_asset_id, binding.index_generation_id),
                )
                row = cur.fetchone()
                if row is None:
                    raise IndexCheckpointConflict("Candidate input has no immutable source render.")
                asset = IndexRenderAsset.model_validate(row["asset_json"])
            fence_index(cur, binding)
            return asset
