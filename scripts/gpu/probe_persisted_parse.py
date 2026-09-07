"""Two authenticated synthetic parses with immutable storage, replay and source scoring."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess  # nosec B404
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.auth import AuthService  # noqa: E402
from lib.auth.models import AuthPrincipal  # noqa: E402
from lib.config import get_settings  # noqa: E402
from lib.db.connection import db_connection  # noqa: E402
from lib.document_parsing.qwen_page_parser import PageGenerationClient  # noqa: E402
from lib.document_processing.models import ProcessingRun  # noqa: E402
from lib.document_processing.parse_execution import execute_parse_candidate  # noqa: E402
from lib.document_processing.parser_configuration import (  # noqa: E402
    DeclaredParserDeployment,
    parser_configuration,
)
from lib.document_processing.service import DocumentProcessingService  # noqa: E402
from lib.documents.access_policy import DocumentAccessContext  # noqa: E402
from lib.evaluation.annotation_render_binding import rebind_annotation_renders  # noqa: E402
from lib.evaluation.annotations import DocumentAnnotation  # noqa: E402
from lib.evaluation.artifact_verification import verify_capture_source  # noqa: E402
from lib.evaluation.capture_models import CaptureDeclaration  # noqa: E402
from lib.evaluation.identity import artifact_digest  # noqa: E402
from lib.evaluation.manifest import (  # noqa: E402
    CaseBinding,
    EvaluationManifest,
    ExposureRecord,
)
from lib.evaluation.persisted_capture import capture_sealed_generation  # noqa: E402
from lib.evaluation.scorer import score_evaluation  # noqa: E402
from lib.jobs import JobService  # noqa: E402
from lib.jobs.lease import keep_job_lease  # noqa: E402
from lib.model_runtime.contracts import (  # noqa: E402
    VisionGenerateRequest,
    VisionGenerateResponse,
)
from lib.model_runtime.ingestion_clients import ingestion_vision_client  # noqa: E402
from lib.storage import ObjectStorage  # noqa: E402
from lib.storage.service import StoredObject  # noqa: E402


def write_private(path: Path, value: object) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(value, output, indent=2, sort_keys=True, allow_nan=False, default=json_identity)
        output.write("\n")


def json_identity(value: object) -> str:
    if isinstance(value, UUID):
        return str(value)
    raise TypeError("Unsupported private report value.")


@dataclass(frozen=True)
class ProbeSource:
    document_id: UUID
    asset_id: UUID
    principal: AuthPrincipal
    storage: ObjectStorage
    stored: StoredObject


class ObservedClient:
    """Count actual adapter calls without logging document text or credentials."""

    def __init__(self, client: PageGenerationClient):
        self.client = client
        self.started = 0
        self.completed = 0

    def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
        if request.max_output_tokens != 8192 or request.temperature != 0:
            raise RuntimeError("Probe generation settings differ from the capture declaration.")
        self.started += 1
        response = self.client.generate(request)
        self.completed += 1
        return response


def register_source(output_dir: Path, original: bytes) -> ProbeSource:
    auth, password = AuthService(), secrets.token_urlsafe(32)
    user = auth.bootstrap_admin(
        email=f"parse-smoke-{uuid4()}@example.com",
        password=password,
        household_name="Isolated parser smoke",
    )
    session = auth.create_password_session(email=user.email, password=password)
    principal = auth.resolve_session_token(session.token)
    if principal is None:
        raise RuntimeError("Isolated authenticated parser principal was not established.")
    storage = ObjectStorage(
        canonical_root=output_dir / "canonical",
        derived_root=output_dir / "derived",
        export_root=output_dir / "exports",
    )
    stored = storage.store_bytes(original, kind="canonical", role="original")
    with db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO documents "
            "(title,ingestion_source,household_id,owner_user_id,original_sha256) "
            "VALUES ('Synthetic source-scored parse','web_upload',%s,%s,%s) RETURNING id",
            (user.household_id, user.user_id, stored.sha256),
        )
        document = cur.fetchone()
        if document is None:
            raise RuntimeError("Isolated document was not registered.")
        cur.execute(
            "INSERT INTO document_assets (document_id,asset_role,uri,mime_type,byte_size,sha256) "
            "VALUES (%s,'original',%s,'image/tiff',%s,%s) RETURNING id",
            (document["id"], stored.uri, stored.byte_size, stored.sha256),
        )
        asset = cur.fetchone()
        if asset is None:
            raise RuntimeError("Isolated original asset was not registered.")
    return ProbeSource(document["id"], asset["id"], principal, storage, stored)


def ingest_and_replay(
    source: ProbeSource,
    client: ObservedClient,
    deployment: DeclaredParserDeployment,
) -> tuple[ProcessingRun, dict[str, object]]:
    service, jobs, queue = DocumentProcessingService(), JobService(), f"parse-smoke-{uuid4()}"
    run = service.start_parse(
        document_id=source.document_id,
        principal=source.principal,
        original_asset_id=source.asset_id,
        original_sha256=source.stored.sha256,
        request_key=uuid4(),
        configuration=parser_configuration(deployment, "image/tiff"),
        queue_name=queue,
    )
    claimed = jobs.claim_next_job_record(worker_name="native-parse-smoke", queue_name=queue)
    if claimed is None or claimed.state.job_id != run.root_job_id:
        raise RuntimeError("Isolated parser job was not claimed with its exact binding.")
    before, completed = client.started, False
    with keep_job_lease(jobs, claimed, worker_name="native-parse-smoke"):
        result = execute_parse_candidate(
            run.binding,
            storage=source.storage,
            client=client,
            deployment=deployment,
            service=service,
            batch_pages=1,
        )
        after_ingest = client.started
        replay = execute_parse_candidate(
            run.binding,
            storage=source.storage,
            client=client,
            deployment=deployment,
            service=service,
            batch_pages=1,
        )
        if (
            replay.new_pages
            or replay.structure_sha256 != result.structure_sha256
            or client.started != after_ingest
            or after_ingest - before != result.page_count
            or client.started != client.completed
        ):
            raise RuntimeError(
                "Candidate inference count or sealed replay differs from its contract."
            )
        jobs.complete_job(
            job_id=claimed.state.job_id,
            claim_token=claimed.claim_token,
            result={"parse_state": "sealed", "page_count": result.page_count},
        )
        completed = True
    if not completed:
        raise RuntimeError("Isolated parser job lost ownership before completion.")
    return run, {
        **asdict(result),
        "actual_adapter_calls": after_ingest - before,
        "replay_adapter_calls": client.started - after_ingest,
    }


def score_persisted_run(
    source: ProbeSource,
    run: ProcessingRun,
    annotation: DocumentAnnotation,
    *,
    output_dir: Path,
    number: int,
    commit: str,
    reference_recorded_at: datetime,
) -> dict[str, object]:
    principal = source.principal
    if principal.household_id is None:
        raise RuntimeError("Isolated parser principal has no household.")
    captured = capture_sealed_generation(
        document_id=source.document_id,
        processing_run_id=run.binding.processing_run_id,
        parse_generation_id=run.binding.parse_generation_id,
        access=DocumentAccessContext(
            principal.household_id, principal.user_id, principal.household_role
        ),
        declaration=CaptureDeclaration(
            item_id=annotation.item_id,
            commit=commit,
            max_output_tokens=8192,
            temperature=0,
        ),
    )
    verified = verify_capture_source(
        captured,
        original_asset_id=source.asset_id,
        original_path=source.stored.path,
    )
    capture, configuration = captured.capture, captured.capture.configuration
    manifest = EvaluationManifest(
        evaluation_id=uuid4(),
        frozen_at=datetime.now(UTC),
        split="synthetic_regression",
        split_revision="persisted-native-smoke-v1",
        cases=(
            CaseBinding(
                item_id=annotation.item_id,
                annotation_sha256=artifact_digest(annotation),
                capture_sha256=artifact_digest(capture),
                original_sha256=annotation.original_sha256,
                processing_run_id=run.binding.processing_run_id,
                parse_generation_id=run.binding.parse_generation_id,
                configuration_sha256=configuration.fingerprint,
                profile=configuration.profile,
                served_model=configuration.served_model,
                source_engine=configuration.source_engine,
                fixture_type="model_backed",
                origin_group=annotation.origin_group,
                template_group=annotation.template_group,
            ),
        ),
        exposures=(
            ExposureRecord(
                item_id=annotation.item_id,
                purpose="evaluation",
                occurred_at=reference_recorded_at,
                actor_reference="structura-persisted-parse-smoke",
            ),
        ),
        development_origin_groups=(annotation.origin_group,),
        development_template_groups=(annotation.template_group,),
    )
    score = score_evaluation(
        manifest,
        [annotation],
        [capture],
        expected_manifest_sha256=artifact_digest(manifest),
    )
    write_private(output_dir / f"capture-{number}.json", capture.model_dump(mode="json"))
    write_private(output_dir / f"manifest-{number}.json", manifest.model_dump(mode="json"))
    write_private(output_dir / f"score-{number}.json", score)
    return {
        "run_status": captured.run_status,
        "source_verification": asdict(verified),
        "coverage": score["documents"][0]["coverage"],
        "parse_tokens": score["documents"][0]["parse_tokens"],
        "searchable_tokens": score["documents"][0]["searchable_tokens"],
    }


def freeze_reference(
    source: ProbeSource,
    *,
    fixture: Path,
    output_dir: Path,
    commit: str,
    annotation: DocumentAnnotation,
) -> tuple[DocumentAnnotation, datetime]:
    rebound = rebind_annotation_renders(
        annotation,
        original_path=source.stored.path,
        original_asset_id=source.asset_id,
        reference_page_paths={
            page.page_number: fixture / f"page-{page.page_number}.png" for page in annotation.pages
        },
    )
    recorded_at = datetime.now(UTC)
    write_private(
        output_dir / "source-annotation-original.json", annotation.model_dump(mode="json")
    )
    write_private(output_dir / "source-annotation.json", rebound.annotation.model_dump(mode="json"))
    write_private(output_dir / "render-binding.json", asdict(rebound.record))
    # Both immutable annotations and the exact-pixel transform are recorded before
    # inference. The later case bundle freezes output hashes after capture.
    write_private(
        output_dir / "pre-inference-reference.json",
        {
            "annotation_sha256": artifact_digest(rebound.annotation),
            "original_annotation_sha256": artifact_digest(annotation),
            "original_sha256": annotation.original_sha256,
            "matching_policy": "structura.parse_matching.v1",
            "threshold_policy": "not_ratified",
            "recorded_at": recorded_at.isoformat(),
            "split": "synthetic_regression",
            "source_commit": commit,
        },
    )
    return rebound.annotation, recorded_at


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--deployment-revision", required=True)
    args = parser.parse_args()
    settings = get_settings()
    if settings.model_mode not in {"live", "required"} or not re.fullmatch(
        r"/structura_it_[a-f0-9]{16}", urlparse(settings.database_url).path
    ):
        parser.error("This smoke requires live models and an explicitly isolated test database.")
    args.output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    # Fixed read-only command in the controlled validation checkout; no shell/input expansion.
    commit = subprocess.check_output(  # nosec B603
        ["/usr/bin/git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        timeout=5,
    ).strip()
    fixture = ROOT / "tests/fixtures/evaluation"
    annotation = DocumentAnnotation.model_validate_json((fixture / "annotation.json").read_text())
    original = (fixture / "original.tiff").read_bytes()
    if hashlib.sha256(original).hexdigest() != annotation.original_sha256:
        raise ValueError("Synthetic original does not match its pre-authored annotation.")
    source = register_source(args.output_dir, original)
    annotation, recorded_at = freeze_reference(
        source,
        fixture=fixture,
        output_dir=args.output_dir,
        commit=commit,
        annotation=annotation,
    )
    deployment = DeclaredParserDeployment(
        mode="live",
        served_model="qwen38-27b-bf16-oxcart",
        revision=args.deployment_revision,
    )
    client = ObservedClient(ingestion_vision_client(settings))
    runs = []
    for number in (1, 2):
        runs.append(ingest_and_replay(source, client, deployment))
        print(f"Synthetic ingest {number} completed and replayed.", flush=True)
    reports = []
    # Read candidate A after supersession; never substitute B's current output.
    for number, (run, result) in enumerate(runs, 1):
        report = score_persisted_run(
            source,
            run,
            annotation,
            output_dir=args.output_dir,
            number=number,
            commit=commit,
            reference_recorded_at=recorded_at,
        )
        reports.append({"execution": result, **report})
    write_private(
        args.output_dir / "report.json",
        {
            "commit": commit,
            "runs": reports,
            "production_activated": False,
            "release_acceptance": "not_evaluated",
        },
    )
    print("Both persisted candidates were source-verified and scored; release gate remains open.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
