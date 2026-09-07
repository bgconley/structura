from __future__ import annotations

import io
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image

from lib.db.connection import db_connection
from lib.document_processing.errors import ProcessingAuthorityLost
from lib.document_processing.parse_execution import execute_parse_candidate
from lib.document_processing.parser_configuration import (
    DeclaredParserDeployment,
    parser_configuration,
)
from lib.document_processing.service import DocumentProcessingService
from lib.document_processing.source_repository import load_processing_source
from lib.model_runtime.contracts import VisionGenerateResponse
from lib.storage import ObjectStorage


class FixtureClient:
    def __init__(self, after_generate=lambda: None, fail_page=None):
        self.calls = []
        self.after_generate = after_generate
        self.fail_page = fail_page

    def generate(self, request):
        number = int(request.prompt.split("Parse page ")[1].split(" ")[0])
        self.calls.append(number)
        if number == self.fail_page:
            raise RuntimeError("Controlled outage")
        data = {"page_number": number, "state": "processed", "diagnostics": [], "elements": []}
        self.after_generate()
        return VisionGenerateResponse(
            profile_name=request.profile_name,
            model_name="qwen38-27b-bf16-oxcart",
            model_version="fixture-v1",
            source_engine="qwen3_8_27b",
            prompt_version=request.prompt_version,
            raw_text=json.dumps(data),
            normalized_json=data,
            confidence_json={},
            input_sha256=tuple(image.sha256 for image in request.image_inputs),
            latency_ms=0,
            finish_reason="stop",
            structured_output_used=True,
        )


@pytest.fixture
def source_execution(processing, tmp_path):
    deployment = DeclaredParserDeployment(
        mode="fixture", served_model="qwen38-27b-bf16-oxcart", revision="postgres-candidate-v1"
    )
    storage = ObjectStorage(
        canonical_root=tmp_path / "canonical",
        derived_root=tmp_path / "derived",
        export_root=tmp_path / "exports",
    )
    buffer = io.BytesIO()
    a, b = Image.new("RGB", (10, 10), "red"), Image.new("RGB", (10, 10), "blue")
    try:
        a.save(buffer, format="TIFF", save_all=True, append_images=[b])
    finally:
        a.close()
        b.close()
    original = storage.store_bytes(buffer.getvalue(), kind="canonical", role="original")
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE document_assets SET uri=%s,sha256=%s,byte_size=%s,mime_type='image/tiff' "
            "WHERE id=%s",
            (original.uri, original.sha256, original.byte_size, processing.asset_id),
        )
        cur.execute(
            "UPDATE documents SET original_sha256=%s,canonical_asset_id=NULL WHERE id=%s",
            (original.sha256, processing.document_id),
        )
    processing.original_sha256 = original.sha256
    processing.configuration = parser_configuration(deployment, "image/tiff")
    return processing, storage, deployment


def execute(run, storage, deployment, client):
    return execute_parse_candidate(
        run.binding,
        storage=storage,
        deployment=deployment,
        client=client,
        service=DocumentProcessingService(),
        batch_pages=1,
    )


def test_exact_registered_source_executes_and_resumes_without_current_pointer(source_execution):
    processing, storage, deployment = source_execution
    run = processing.start()
    claimed = processing.claim()
    with processing.scope(claimed):
        original = load_processing_source(run.binding)
        assert original.original_asset_id == processing.asset_id
        with pytest.raises(RuntimeError, match="outage"):
            execute(run, storage, deployment, FixtureClient(fail_page=2))
        resumed = FixtureClient()
        result = execute(run, storage, deployment, resumed)
        replay = execute(run, storage, deployment, FixtureClient(fail_page=1))
    assert resumed.calls == [2]
    assert (result.resumed_pages, result.new_pages) == (1, 1)
    assert replay.structure_sha256 == result.structure_sha256
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT state,structure_sha256 FROM document_parse_generations WHERE id=%s",
            (run.binding.parse_generation_id,),
        )
        assert cur.fetchone() == {"state": "sealed", "structure_sha256": result.structure_sha256}
        cur.execute(
            "SELECT canonical_asset_id FROM documents WHERE id=%s", (processing.document_id,)
        )
        assert cur.fetchone()["canonical_asset_id"] is None
        for table in ["document_pages", "canonical_fields", "document_extractions"]:
            cur.execute(
                f"SELECT count(*) AS n FROM {table} WHERE document_id=%s", (processing.document_id,)
            )
            assert cur.fetchone()["n"] == 0


def test_run_supersession_during_model_call_rejects_checkpoint_and_next_page(source_execution):
    processing, storage, deployment = source_execution
    old = processing.start()
    claimed = processing.claim()
    # Another authorized request must finish while the model call is in flight;
    # this also proves no document/run transaction remains open around inference.
    with ThreadPoolExecutor(max_workers=1) as pool:
        client = FixtureClient(
            after_generate=lambda: pool.submit(processing.start).result(timeout=5)
        )
        with processing.scope(claimed), pytest.raises(ProcessingAuthorityLost):
            execute(old, storage, deployment, client)
    assert client.calls == [1]
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM document_parse_page_checkpoints "
            "WHERE parse_generation_id=%s",
            (old.binding.parse_generation_id,),
        )
        assert cur.fetchone()["n"] == 0
        cur.execute(
            "SELECT status,claim_token FROM pipeline_jobs WHERE id=%s", (claimed.state.job_id,)
        )
        job = cur.fetchone()
        assert job["status"] == "running" and job["claim_token"] == claimed.claim_token
