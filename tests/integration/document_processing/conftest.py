from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from threading import Event
from uuid import uuid4

import pytest

from lib.auth import AuthService
from lib.config import get_settings
from lib.db.connection import db_connection
from lib.document_parsing.model_output import PageParseOutput
from lib.document_parsing.normalization import normalize_page
from lib.document_parsing.qwen_page_parser import ParsedSourcePage
from lib.document_parsing.searchable_text import page_chunks
from lib.document_parsing.structure import (
    DocumentStructure,
    ParseInvocation,
    SourceInventory,
    SourcePage,
    SourceRender,
)
from lib.document_processing.models import ParseConfiguration
from lib.document_processing.service import DocumentProcessingService
from lib.documents.access_policy import DocumentAccessContext
from lib.jobs import JobService
from lib.jobs.ownership import JobAttempt, job_attempt_scope


@dataclass
class ProcessingHarness:
    access: DocumentAccessContext
    document_id: object
    asset_id: object
    original_sha256: str
    queue: str
    configuration: ParseConfiguration
    inventory: SourceInventory

    def start(self, **overrides):
        return DocumentProcessingService().start_parse(
            **{
                "document_id": self.document_id,
                "access": self.access,
                "original_asset_id": self.asset_id,
                "original_sha256": self.original_sha256,
                "request_key": uuid4(),
                "configuration": self.configuration,
                "queue_name": self.queue,
                **overrides,
            }
        )

    def claim(self):
        claimed = JobService().claim_next_job_record(worker_name="candidate", queue_name=self.queue)
        assert claimed
        return claimed

    def scope(self, claimed):
        return job_attempt_scope(JobAttempt(claimed.state.job_id, claimed.claim_token), Event())

    def checkpoint(self, run, *, text="Original text", page_number=1):
        output = PageParseOutput.model_validate(
            {
                "page_number": page_number,
                "state": "processed",
                "diagnostics": [],
                "elements": [
                    {
                        "kind": "paragraph",
                        "text": text,
                        "bbox": {"left": 0, "top": 0, "right": 900, "bottom": 900},
                        "parent_index": None,
                        "table": None,
                    }
                ],
            }
        )
        raw = output.model_dump_json()
        source = SourceRender(
            page_number=page_number,
            image_sha256="b" * 64,
            pixel_width=200,
            pixel_height=100,
            renderer=self.configuration.renderer,
            renderer_version=self.configuration.renderer_version,
        )
        invocation = ParseInvocation(
            request_id=uuid4(),
            page_numbers=(page_number,),
            profile=self.configuration.profile,
            served_model=self.configuration.served_model,
            source_engine=self.configuration.source_engine,
            prompt_version=self.configuration.prompt_version,
            output_schema_version=self.configuration.output_schema_version,
            raw_output_sha256=hashlib.sha256(raw.encode()).hexdigest(),
            finish_reason="stop",
            latency_ms=1,
        )
        return ParsedSourcePage(
            normalize_page(output, source, run.binding.parse_generation_id), invocation, raw
        )

    def structure(self, run, checkpoints):
        return DocumentStructure(
            parse_generation_id=run.binding.parse_generation_id,
            processing_run_id=run.binding.processing_run_id,
            source=self.inventory,
            pages=tuple(item.page for item in checkpoints),
            invocations=tuple(item.invocation for item in checkpoints),
            chunks=tuple(
                chunk
                for item in checkpoints
                for chunk in page_chunks(item.page, run.binding.parse_generation_id)
            ),
        )


@pytest.fixture
def processing(monkeypatch):
    url = os.environ.get("STRUCTURA_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires an isolated database migrated through 096.")
    monkeypatch.setenv("STRUCTURA_DATABASE_URL", url)
    monkeypatch.setenv("STRUCTURA_ENV", "test")
    get_settings.cache_clear()
    owner = AuthService().bootstrap_admin(
        email=f"processing-{uuid4()}@example.com",
        password="minimum8",
        household_name="Processing",
    )
    original = b"controlled source identity for database tests"
    digest = hashlib.sha256(original).hexdigest()
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO documents
            (title, ingestion_source, household_id, owner_user_id, original_sha256)
            VALUES ('Retained original', 'web_upload', %s, %s, %s) RETURNING id""",
            (owner.household_id, owner.user_id, digest),
        )
        document_id = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO document_assets
            (document_id, asset_role, uri, mime_type, byte_size, sha256)
            VALUES (%s, 'original', %s, 'image/png', %s, %s) RETURNING id""",
            (document_id, f"object://test/{uuid4()}", len(original), digest),
        )
        asset_id = cur.fetchone()["id"]
        cur.execute(
            "UPDATE documents SET canonical_asset_id = %s WHERE id = %s", (asset_id, document_id)
        )
    configuration = ParseConfiguration(
        profile="qwen-native-test",
        served_model="qwen38-27b-bf16-oxcart",
        source_engine="qwen3_8_27b",
        model_revision="test-revision",
        prompt_version="qwen-native-page-v1",
        output_schema_version="structura.page_parse.v1",
        normalizer_version="v1",
        chunker_version="v1",
        renderer="test-source-raster",
        renderer_version="v1",
        render_scale=2,
    )
    yield ProcessingHarness(
        # bootstrap_admin persists an owner membership; BootstrapResult contains IDs only.
        DocumentAccessContext(owner.household_id, owner.user_id, "owner"),
        document_id,
        asset_id,
        digest,
        f"processing-{uuid4()}",
        configuration,
        SourceInventory(
            original_asset_id=asset_id,
            original_sha256=digest,
            mime_type="image/png",
            byte_size=len(original),
            pages=(SourcePage(page_number=1, width=200, height=100, unit="pixels"),),
        ),
    )
    get_settings.cache_clear()
