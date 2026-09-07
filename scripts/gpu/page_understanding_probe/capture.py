"""Authorized persisted capture, original verification and separate exposed diagnostics."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from lib.document_parsing.page_understanding.codec import decode_page_understanding
from lib.document_processing.configuration_types import ParseConfigurationV2
from lib.document_processing.models import ProcessingRun
from lib.documents.access_policy import DocumentAccessContext
from lib.evaluation.annotations import DocumentAnnotation
from lib.evaluation.artifact_verification import verify_capture_source
from lib.evaluation.capture_models import CaptureDeclaration
from lib.evaluation.identity import artifact_digest
from lib.evaluation.manifest import CaseBinding, EvaluationManifest, ExposureRecord
from lib.evaluation.persisted_capture import capture_sealed_generation
from lib.evaluation.scorer import score_evaluation
from scripts.gpu.page_understanding_probe.scoring import score_page
from scripts.gpu.probe_persisted_parse import ProbeSource, write_private
from scripts.gpu.probe_retained_evidence import verify_historical_api


def capture_and_score(
    source: ProbeSource,
    run: ProcessingRun,
    configuration: ParseConfigurationV2,
    annotation: DocumentAnnotation,
    expectations: dict[str, Any],
    *,
    output: Path,
    commit: str,
    reference_recorded_at: datetime,
) -> dict[str, Any]:
    household = source.principal.household_id
    if household is None:
        raise RuntimeError("Probe source requires its authenticated household.")
    # This deliberately supersedes the candidate with a cancelled, unclaimed
    # successor (zero HTTP). The exact historical generation must remain readable.
    historical = verify_historical_api(run, source, output)
    persisted = capture_sealed_generation(
        document_id=source.document_id,
        processing_run_id=run.binding.processing_run_id,
        parse_generation_id=run.binding.parse_generation_id,
        access=DocumentAccessContext(
            household, source.principal.user_id, source.principal.household_role
        ),
        declaration=CaptureDeclaration(
            item_id=annotation.item_id,
            commit=commit,
            max_output_tokens=configuration.request.max_output_tokens,
            temperature=configuration.request.temperature,
        ),
    )
    capture = persisted.capture
    if (
        capture.configuration != configuration
        or persisted.run_status != "superseded"
        or persisted.generation_settings_provenance != "frozen_configuration"
        or len(capture.raw_pages) != 3
    ):
        raise RuntimeError("Persisted capture differs from the exact frozen historical run.")
    verified = verify_capture_source(
        persisted,
        original_asset_id=source.asset_id,
        original_path=source.stored.path,
    )
    manifest = EvaluationManifest(
        evaluation_id=uuid4(),
        frozen_at=datetime.now(UTC),
        split="synthetic_regression",
        split_revision="exposed-page-understanding-smoke-v1",
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
                actor_reference="structura-exposed-page-understanding-probe",
            ),
        ),
        development_origin_groups=(annotation.origin_group,),
        development_template_groups=(annotation.template_group,),
    )
    structural = score_evaluation(
        manifest,
        [annotation],
        [capture],
        expected_manifest_sha256=artifact_digest(manifest),
    )
    typed = {
        "scope": "three exposed synthetic pages; annotated-obligation recall and physical grouping",
        "pages": [
            score_page(decode_page_understanding(raw.raw_output).page, expected)
            for raw, expected in zip(capture.raw_pages, expectations["pages"], strict=True)
        ],
        "threshold_policy": "not_ratified",
        "overall_precision": "not_evaluated",
        "visual_support": "not_evaluated",
        "calibration": "not_evaluated",
        "release_acceptance": "not_evaluated",
    }
    write_private(output / "capture.json", capture.model_dump(mode="json"))
    write_private(output / "manifest.json", manifest.model_dump(mode="json"))
    write_private(output / "structural-score.json", structural)
    write_private(output / "understanding-score.json", typed)
    return {
        "historical_evidence_api": historical,
        "source_verification": asdict(verified),
        "capture_sha256": artifact_digest(capture),
        "manifest_sha256": artifact_digest(manifest),
        "configuration_sha256": configuration.fingerprint,
        "commit_provenance": persisted.commit_provenance,
        "generation_settings_provenance": persisted.generation_settings_provenance,
        "invocation_authenticity_from_db_capture": persisted.invocation_authenticity,
        "structural_report": "structural-score.json",
        "understanding_report": "understanding-score.json",
        "manifest_timing": "post-inference bundle pin; source annotations frozen before calls",
    }
