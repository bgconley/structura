"""Three exposed synthetic pages: combined v2 candidate, exact capture and retained evidence.

This diagnostic never activates a pipeline, publishes facts, or supplies a release gate.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.config import get_settings  # noqa: E402
from lib.document_processing.configuration_types import ParseRequestSettings  # noqa: E402
from lib.document_processing.errors import ProcessingError  # noqa: E402
from lib.document_processing.parser_configuration import DeclaredParserDeployment  # noqa: E402
from lib.model_runtime.clients.qwen_vl import QwenVLClient  # noqa: E402
from lib.model_runtime.credentials import model_api_key  # noqa: E402
from lib.model_runtime.http_client import ModelProtocolError, ModelTimeoutError  # noqa: E402
from lib.model_runtime.profiles import get_model_profile  # noqa: E402
from scripts.gpu.page_understanding_probe.capture import capture_and_score  # noqa: E402
from scripts.gpu.page_understanding_probe.execution import (  # noqa: E402
    ingest_and_replay,
    prepare_configuration,
)
from scripts.gpu.page_understanding_probe.inputs import (  # noqa: E402
    FIXTURE,
    load_inputs,
    preflight,
)
from scripts.gpu.page_understanding_probe.observations import (  # noqa: E402
    ObservedClient,
    ObservedTransport,
)
from scripts.gpu.probe_persisted_parse import (  # noqa: E402
    freeze_reference,
    register_source,
    write_private,
)


@dataclass
class ProbeProgress:
    stage: str = "request_configuration"
    owns_directory: bool = False


def record_failed_stage(output: Path, progress: ProbeProgress, failure: Exception) -> None:
    """A fresh private diagnostic namespace only; never append to a prior probe."""
    code = "probe_stage_failed"
    if isinstance(failure, ModelProtocolError):
        code = "model_protocol_rejected"
    elif isinstance(failure, ModelTimeoutError):
        code = "model_timeout"
    elif isinstance(failure, ProcessingError):
        code = "processing_contract_rejected"
    try:
        if not progress.owns_directory:
            output.mkdir(mode=0o700, parents=False, exist_ok=False)
            progress.owns_directory = True
        write_private(
            output / "failed-stage.json",
            {
                "stage": progress.stage,
                "code": code,
                "execution_complete": False,
                "release_acceptance": "not_evaluated",
                "production_activated": False,
                "exception_text_retained": False,
            },
        )
    except OSError:
        # Existing/unwritable paths are not ours to modify. Console stays static.
        return


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--deployment-revision", required=True)
    parser.add_argument("--max-output-tokens", type=int, required=True)
    parser.add_argument("--temperature", type=float, required=True)
    parser.add_argument(
        "--seed", required=True, help="Explicit integer or 'none' to omit the seed."
    )
    parser.add_argument("--timeout-seconds", type=int, required=True)
    return parser.parse_args()


def run(args: argparse.Namespace, progress: ProbeProgress) -> None:
    settings = get_settings()
    request = ParseRequestSettings(
        max_output_tokens=args.max_output_tokens,
        temperature=args.temperature,
        seed=None if args.seed == "none" else int(args.seed),
        timeout_seconds=args.timeout_seconds,
    )
    profile = get_model_profile(settings.model_ingestion_profile)
    if profile.served_model_name is None:
        raise RuntimeError("Probe requires the accepted named ingestion deployment.")
    deployment = DeclaredParserDeployment(
        mode="live",
        served_model=profile.served_model_name,
        revision=args.deployment_revision,
    )
    progress.stage = "frozen_source_verification"
    inputs = load_inputs()
    progress.stage = "runtime_and_checkout_preflight"
    commit = preflight(settings, args.output_dir, args.expected_commit)
    args.output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    progress.owns_directory = True
    # The original is a byte-for-byte verified raw TIFF reconstruction from the
    # committed grayscale PNGs. No labels are derived from a model response.
    progress.stage = "isolated_source_admission"
    source = register_source(args.output_dir, inputs.original)
    progress.stage = "pre_inference_source_rebinding"
    annotation, recorded_at = freeze_reference(
        source,
        fixture=FIXTURE,
        output_dir=args.output_dir,
        commit=commit,
        annotation=inputs.annotation,
    )
    progress.stage = "frozen_parser_configuration"
    configuration = prepare_configuration(source, deployment, request)
    write_private(args.output_dir / "configuration.json", configuration.model_dump(mode="json"))
    write_private(args.output_dir / "expectations.json", inputs.expectations)
    write_private(
        args.output_dir / "pre-inference-policy.json",
        {
            "source_commit": commit,
            "configuration_sha256": configuration.fingerprint,
            "reference_recorded_at": recorded_at.isoformat(),
            "maximum_actual_http_attempts": 3,
            "source_pages": 3,
            "split": "synthetic_regression",
            "exposure": "visible_development_cases",
            "threshold_policy": "not_ratified",
            "request": request.model_dump(mode="json"),
            "original_byte_size": len(inputs.original),
            "original_sha256": source.stored.sha256,
            "source_transport": "grayscale_raw_tiff_rebuilt_from_committed_reference_pngs",
            "weight_revision_provenance": "externally_declared_not_weight_hash_attestation",
        },
    )
    progress.stage = "authenticated_adapter_configuration"
    transport = ObservedTransport(args.output_dir)
    client = ObservedClient(
        QwenVLClient(
            profile=profile,
            http_client_base_url=settings.model_ingestion_url,
            api_key=model_api_key(
                settings.model_ingestion_api_key, settings.model_ingestion_api_key_file
            ),
            transport=transport,
        ),
        request,
        args.output_dir,
    )
    try:
        progress.stage = "candidate_parse_replay_and_retention"
        candidate, execution = ingest_and_replay(
            source,
            configuration,
            deployment,
            client,
            transport,
            args.output_dir,
        )
        progress.stage = "historical_capture_and_scoring"
        evidence = capture_and_score(
            source,
            candidate,
            configuration,
            annotation,
            inputs.expectations,
            output=args.output_dir,
            commit=commit,
            reference_recorded_at=recorded_at,
        )
        if (transport.started, client.started) != (3, 3):
            raise RuntimeError("Post-capture model call budget differs.")
        progress.stage = "final_report"
        write_private(
            args.output_dir / "report.json",
            {
                "source_commit": commit,
                "execution": execution,
                "evidence": evidence,
                "execution_complete": True,
                "production_activated": False,
                "release_acceptance": "not_evaluated",
                "calibration": "not_evaluated",
                "evidence_scope": "three exposed synthetic source pages; no blind holdout",
            },
        )
    except Exception:
        write_private(
            args.output_dir / "failure.json",
            {
                "execution_complete": False,
                "actual_http_attempts": transport.started,
                "actual_http_responses": transport.responses,
                "actual_adapter_attempts": client.started,
                "actual_adapter_responses": client.completed,
                "production_activated": False,
                "release_acceptance": "not_evaluated",
                "diagnostic_body_limit_bytes": 1024 * 1024,
                "note": "Private observations may be incomplete; no output is repaired or retried.",
            },
        )
        raise
    finally:
        transport.close()


def main() -> int:
    args = arguments()
    progress = ProbeProgress()
    try:
        run(args, progress)
    except Exception as failure:
        record_failed_stage(args.output_dir, progress, failure)
        # Connection strings, credentials and document/model text stay out of logs.
        print(
            "Bounded page-understanding probe failed; inspect its private diagnostics.",
            file=sys.stderr,
        )
        return 1
    print("Three-page diagnostic completed; production and release acceptance remain unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
