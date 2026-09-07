"""Bounded transaction wrappers for candidate-only processing; never selects current structure."""

from __future__ import annotations

from uuid import UUID

from lib.auth.models import AuthPrincipal
from lib.db.connection import db_connection
from lib.document_parsing.qwen_page_parser import ParsedSourcePage
from lib.document_parsing.structure import DocumentStructure, SourceInventory
from lib.document_processing import checkpoint_repository, run_repository
from lib.document_processing.authority_repository import fence_processing_attempt, lock_current_run
from lib.document_processing.models import ParseConfiguration, ProcessingBinding, ProcessingRun
from lib.documents.access_policy import DocumentAccessContext


class DocumentProcessingService:
    def start_parse(
        self,
        *,
        document_id: UUID,
        principal: AuthPrincipal,
        original_asset_id: UUID,
        original_sha256: str,
        request_key: UUID,
        configuration: ParseConfiguration,
        queue_name: str = "document-parsing-candidates",
    ) -> ProcessingRun:
        with db_connection() as conn, conn.cursor() as cur:
            run = run_repository.start_parse_run(
                cur,
                document_id=document_id,
                principal=principal,
                original_asset_id=original_asset_id,
                original_sha256=original_sha256,
                request_key=request_key,
                configuration=configuration,
                queue_name=queue_name,
            )
            conn.commit()
        return run

    def cancel(self, binding: ProcessingBinding, access: DocumentAccessContext) -> None:
        with db_connection() as conn, conn.cursor() as cur:
            run_repository.cancel_parse_run(cur, binding, access)
            conn.commit()

    def assert_authority(self, binding: ProcessingBinding) -> None:
        with db_connection(connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '5s'")
            cur.execute("SET LOCAL lock_timeout = '2s'")
            lock_current_run(cur, binding)
            fence_processing_attempt(cur, binding)

    def initialize_inventory(self, binding: ProcessingBinding, inventory: SourceInventory) -> None:
        with db_connection() as conn, conn.cursor() as cur:
            checkpoint_repository.initialize_inventory(cur, binding, inventory)
            fence_processing_attempt(cur, binding)
            conn.commit()

    def checkpoint(self, binding: ProcessingBinding, checkpoint: ParsedSourcePage) -> None:
        with db_connection() as conn, conn.cursor() as cur:
            checkpoint_repository.persist_checkpoint(cur, binding, checkpoint)
            fence_processing_attempt(cur, binding)
            conn.commit()

    def load_checkpoints(self, binding: ProcessingBinding) -> tuple[ParsedSourcePage, ...]:
        with db_connection() as conn, conn.cursor() as cur:
            checkpoints = checkpoint_repository.list_checkpoints(cur, binding)
            fence_processing_attempt(cur, binding)
            return checkpoints

    def seal(self, binding: ProcessingBinding, structure: DocumentStructure) -> str:
        with db_connection() as conn, conn.cursor() as cur:
            digest = checkpoint_repository.seal_generation(cur, binding, structure)
            fence_processing_attempt(cur, binding)
            conn.commit()
        return digest
