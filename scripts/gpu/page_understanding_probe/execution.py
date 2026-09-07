"""One three-page candidate under a renewing claim, retained evidence before ACK."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from lib.config import get_settings
from lib.db.connection import db_connection
from lib.document_parsing.source_adapter import DocumentSource
from lib.document_processing.configuration_types import ParseConfigurationV2, ParseRequestSettings
from lib.document_processing.models import ProcessingRun
from lib.document_processing.parse_execution import execute_parse_candidate
from lib.document_processing.parser_configuration import DeclaredParserDeployment
from lib.document_processing.service import DocumentProcessingService
from lib.document_processing.understanding_configuration import understanding_configuration
from lib.jobs import JobService
from lib.jobs.lease import keep_job_lease
from scripts.gpu.page_understanding_probe.observations import ObservedClient, ObservedTransport
from scripts.gpu.probe_database import assert_isolated_connection, isolated_database_name
from scripts.gpu.probe_persisted_parse import ProbeSource, write_private
from scripts.gpu.probe_retained_evidence import retain_and_replay


def prepare_configuration(
    source: ProbeSource, deployment: DeclaredParserDeployment, request: ParseRequestSettings
) -> ParseConfigurationV2:
    with DocumentSource(
        source.stored.path,
        asset_id=source.asset_id,
        expected_sha256=source.stored.sha256,
        mime_type="image/tiff",
        max_bytes=source.stored.byte_size,
    ) as original:
        if len(original.inventory.pages) != 3:
            raise RuntimeError("Probe original must contain exactly three source pages.")
        return understanding_configuration(deployment, original, request=request)


def ingest_and_replay(
    source: ProbeSource,
    configuration: ParseConfigurationV2,
    deployment: DeclaredParserDeployment,
    client: ObservedClient,
    transport: ObservedTransport,
    output: Path,
) -> tuple[ProcessingRun, dict[str, Any]]:
    service, jobs = DocumentProcessingService(), JobService()
    queue = f"page-understanding-probe-{uuid4()}"
    run = service.start_parse(
        document_id=source.document_id,
        principal=source.principal,
        original_asset_id=source.asset_id,
        original_sha256=source.stored.sha256,
        request_key=uuid4(),
        configuration=configuration,
        queue_name=queue,
    )
    write_private(output / "run.json", asdict(run))
    claimed = jobs.claim_next_job_record(worker_name="understanding-probe", queue_name=queue)
    if claimed is None or claimed.state.job_id != run.root_job_id:
        raise RuntimeError("Probe did not acquire the exact isolated producer claim.")
    acknowledged = False
    try:
        with keep_job_lease(jobs, claimed, worker_name="understanding-probe"):
            result = execute_parse_candidate(
                run.binding,
                storage=source.storage,
                client=client,
                deployment=deployment,
                service=service,
                batch_pages=1,
            )
            before_replay = client.started, transport.started
            replay = execute_parse_candidate(
                run.binding,
                storage=source.storage,
                client=client,
                deployment=deployment,
                service=service,
                batch_pages=1,
            )
            if (
                result.page_count != 3
                or result.new_pages != 3
                or replay.new_pages
                or replay.resumed_pages != 3
                or replay.structure_sha256 != result.structure_sha256
                or (client.started, transport.started) != before_replay
                or (client.started, client.completed, transport.started, transport.responses)
                != (3, 3, 3, 3)
            ):
                raise RuntimeError("Probe page inventory, actual attempts or sealed replay differ.")
            retained = retain_and_replay(run, source)
            snapshot_generation(run, output / "persisted-generation.json")
            # A sealed parse alone is insufficient for ACK in this diagnostic:
            # all source renders must also be durably retained and replayable.
            jobs.complete_job(
                job_id=claimed.state.job_id,
                claim_token=claimed.claim_token,
                result={"parse_state": "sealed", "page_count": 3},
            )
            acknowledged = True
        if not acknowledged:
            # The shared lease context intentionally absorbs ownership loss.
            # That is a failed probe, never an implicit successful ACK.
            raise RuntimeError("Producer ownership was lost before the probe ACK.")
    except Exception:
        # Exact-run private diagnosis remains available after authority is lost.
        # No repaired output, ACK, implicit retry, or fallback model invocation.
        recovery: dict[str, bool] = {}
        try:
            snapshot_generation(run, output / "failed-generation.json")
            recovery["persisted_snapshot_retained"] = True
        except Exception:
            recovery["persisted_snapshot_retained"] = False
        try:
            jobs.fail_job(
                job_id=claimed.state.job_id,
                claim_token=claimed.claim_token,
                error_class="probe_execution_failed",
                message="Bounded diagnostic failed.",
                retryable=False,
            )
            recovery["failure_recorded_under_claim"] = True
        except Exception:
            recovery["failure_recorded_under_claim"] = False
        write_private(output / "failure-lifecycle.json", recovery)
        raise
    return run, {
        "parse": asdict(result),
        "replay": asdict(replay),
        "actual_adapter_attempts": client.started,
        "actual_adapter_responses": client.completed,
        "actual_http_attempts": transport.started,
        "actual_http_responses": transport.responses,
        "replay_adapter_attempts": 0,
        "replay_http_attempts": 0,
        "retained_evidence_before_ack": retained,
    }


def snapshot_generation(run: ProcessingRun, output: Path) -> None:
    """Operator-only isolated probe read, exact IDs; not an application ACL API.

    This can retain incomplete/failed diagnostic material and does not certify it
    as a validated capture. The authorized sealed capture is a separate step.
    """
    database = get_settings().database_url
    expected = isolated_database_name(database)
    binding = run.binding
    with db_connection(database, connect_timeout=5) as conn, conn.cursor() as cur:
        assert_isolated_connection(conn, expected)
        cur.execute("SET LOCAL statement_timeout = '5s'")
        cur.execute(
            "SELECT r.config_json,r.config_sha256,r.status,g.state,g.inventory_json,"
            "g.inventory_sha256,g.structure_json,g.structure_sha256 "
            "FROM document_processing_runs r JOIN document_parse_generations g "
            "ON g.creator_run_id=r.id AND g.document_id=r.document_id "
            "WHERE r.id=%s AND r.document_id=%s AND g.id=%s AND r.parse_generation_id=g.id",
            (binding.processing_run_id, binding.document_id, binding.parse_generation_id),
        )
        record = cur.fetchone()
        if record is None:
            raise RuntimeError("Exact diagnostic generation is unavailable.")
        cur.execute(
            "SELECT page_number,page_id,page_json,invocation_json,raw_output,content_sha256 "
            "FROM document_parse_page_checkpoints WHERE parse_generation_id=%s "
            "ORDER BY page_number LIMIT 4",
            (binding.parse_generation_id,),
        )
        pages = cur.fetchall()
        if len(pages) > 3:
            raise RuntimeError("Probe checkpoint inventory exceeds the frozen source.")
    write_private(
        output,
        {
            "binding": asdict(binding),
            "record": record,
            "checkpoints": pages,
            "purpose": "exact_persisted_diagnostic_not_validated_capture",
        },
    )
