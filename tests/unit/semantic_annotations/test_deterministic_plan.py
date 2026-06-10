from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from uuid import uuid4

from lib.extraction.models import (
    ExtractionSourceDocument,
    ParsedElementText,
    ParsedPageText,
    ParsedTableText,
)
from lib.semantic_annotations.deterministic_plan import (
    apply_baseline_invariant,
    baseline_only_result,
    baseline_plan_fingerprint,
    deterministic_baseline_manifest,
)
from lib.semantic_annotations.models import (
    SemanticAnnotationResult,
    SemanticGroundingRef,
    SemanticRegionAnnotation,
)

FIXTURES = Path("tests/fixtures/text_lane")

_INVOICE_TEXT = (
    "Invoice 6046058/1 for service and parts. "
    "Subtotal 701.50 due upon receipt. Invoice number, invoice date and "
    "amount due are shown above. Bill to: Example Customer."
)


def _table(page_number: int = 1) -> ParsedTableText:
    payload = json.loads((FIXTURES / "service_lines_grid.json").read_text())
    return ParsedTableText(
        table_id=uuid4(),
        page_number=page_number,
        table_index=payload["table_index"],
        table_markdown="| DESCRIPTION | | AMOUNT |\n| --- | --- | --- |\n| svc | 1 | 289.00 |",
        table_json=payload["table_json"],
        element_id=uuid4(),
    )


def _source(tables: list[ParsedTableText]) -> ExtractionSourceDocument:
    return ExtractionSourceDocument(
        document_id=uuid4(),
        household_id=uuid4(),
        title="Service invoice",
        original_filename="service-invoice.pdf",
        mime_type="application/pdf",
        family="invoice",
        subtype=None,
        sensitivity="standard",
        document_date=date(2026, 6, 1),
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=[
            ParsedPageText(
                page_id=uuid4(),
                page_number=1,
                text=_INVOICE_TEXT,
                has_text_layer=True,
            )
        ],
        elements=[
            ParsedElementText(element_id=uuid4(), page_number=1, ordinal=1, text=_INVOICE_TEXT)
        ],
        tables=tables,
    )


def test_baseline_manifest_plans_tables_without_a_model() -> None:
    source = _source([_table()])
    baseline = deterministic_baseline_manifest(source)
    assert baseline.source_engine == "docling_baseline"
    assert baseline.regions, "table-bearing source must produce baseline regions"
    table_region = baseline.regions[0]
    assert table_region.grounding.table_id == source.tables[0].table_id
    assert table_region.granite_task == "tables_json"
    assert table_region.semantic_type.endswith("_line_item_table")


def test_baseline_fingerprint_is_stable_across_reingests() -> None:
    # Same parse content, fresh UUIDs (a new ingest) -> identical fingerprint.
    first_source = _source([_table()])
    second_source = _source([_table()])
    first = deterministic_baseline_manifest(first_source)
    second = deterministic_baseline_manifest(second_source)
    assert baseline_plan_fingerprint(first_source, first) == baseline_plan_fingerprint(
        second_source, second
    )
    # A structurally different parse changes the fingerprint.
    two_tables = _source([_table(), _table(page_number=2)])
    third = deterministic_baseline_manifest(two_tables)
    assert baseline_plan_fingerprint(two_tables, third) != baseline_plan_fingerprint(
        first_source, first
    )


def test_invariant_appends_uncovered_baseline_regions() -> None:
    source = _source([_table()])
    baseline = deterministic_baseline_manifest(source)
    stripped = SemanticAnnotationResult(
        manifest=baseline.__class__(
            document_id=baseline.document_id,
            household_id=baseline.household_id,
            quality_mode=baseline.quality_mode,
            profile_name="qwen",
            source_engine="qwen3_vl_8b",
            model_name="qwen",
            model_version="t",
            prompt_version="t",
            pages=baseline.pages,
            regions=[],
            confidence={},
            manifest={"regions": [], "pages": []},
        )
    )
    enforced = apply_baseline_invariant(source, baseline, stripped)
    telemetry = enforced.manifest.manifest["deterministic_baseline"]
    assert telemetry["enforced_region_count"] == len(baseline.regions)
    assert len(enforced.manifest.regions) == len(baseline.regions)
    assert telemetry["fingerprint"] == baseline_plan_fingerprint(source, baseline)


def test_invariant_counts_qwen_covered_tables_as_covered() -> None:
    source = _source([_table()])
    baseline = deterministic_baseline_manifest(source)
    qwen_region = SemanticRegionAnnotation(
        semantic_type="invoice_line_item_table",
        priority="critical",
        granite_task="tables_json",
        grounding=SemanticGroundingRef(kind="table", table_id=source.tables[0].table_id),
        target_schema="invoice",
        expected_fields=("description", "amount"),
    )
    covered = SemanticAnnotationResult(
        manifest=baseline.__class__(
            document_id=baseline.document_id,
            household_id=baseline.household_id,
            quality_mode=baseline.quality_mode,
            profile_name="qwen",
            source_engine="qwen3_vl_8b",
            model_name="qwen",
            model_version="t",
            prompt_version="t",
            pages=baseline.pages,
            regions=[qwen_region],
            confidence={},
            manifest={"regions": [], "pages": []},
        )
    )
    enforced = apply_baseline_invariant(source, baseline, covered)
    telemetry = enforced.manifest.manifest["deterministic_baseline"]
    assert telemetry["enforced_region_count"] == 0
    assert enforced.manifest.regions == [qwen_region]


def test_baseline_only_result_marks_review_and_succeeds() -> None:
    source = _source([_table()])
    baseline = deterministic_baseline_manifest(source)
    result = baseline_only_result(
        source, baseline, failure_reason="ModelTimeoutError: qwen unreachable"
    )
    assert result.status == "succeeded"
    assert result.manifest.review_required is True
    assert result.manifest.escalation_reason is not None
    assert result.manifest.escalation_reason.startswith("qwen_annotation_failed:")
    telemetry = result.manifest.manifest["deterministic_baseline"]
    assert telemetry["qwen_annotation_failed"] is True
    assert result.manifest.regions == baseline.regions


class _FailingGateway:
    def annotate(self, source, *, quality_mode):  # noqa: ANN001, ANN003
        from lib.model_runtime.http_client import ModelProtocolError

        raise ModelProtocolError("qwen semantic service unreachable")


class _EmptyManifestGateway:
    def annotate(self, source, *, quality_mode):  # noqa: ANN001, ANN003
        from lib.semantic_annotations.models import DocumentSemanticManifest

        manifest = DocumentSemanticManifest(
            document_id=source.document_id,
            household_id=source.household_id,
            quality_mode=quality_mode,
            profile_name="qwen3-vl-8b-fp8-semantic:v1",
            source_engine="qwen3_vl_8b",
            model_name="qwen",
            model_version="t",
            prompt_version="phase8_5-semantic-smart-v3",
            pages=[],
            regions=[],
            confidence={},
            manifest={"document_type": "invoice", "pages": [], "regions": []},
        )
        return SemanticAnnotationResult(manifest=manifest)


class _RecordingJobs:
    def __init__(self) -> None:
        self.created: list[dict] = []

    def create_job(self, **kwargs):  # noqa: ANN003
        from types import SimpleNamespace

        self.created.append(kwargs)
        return SimpleNamespace(job_id=kwargs.get("job_id"))


def _service_with(gateway, source, jobs):  # noqa: ANN001
    from lib.semantic_annotations.repository import PersistedSemanticManifest
    from lib.semantic_annotations.service import SemanticAnnotationService

    return SemanticAnnotationService(
        source_loader=lambda _document_id: source,
        gateway=gateway,
        manifest_persister=lambda manifest: PersistedSemanticManifest(
            annotation_id=uuid4(),
            region_ids=tuple(uuid4() for _ in manifest.regions),
        ),
        jobs=jobs,
    )


def _with_planner_flag(monkeypatch, enabled: bool):  # noqa: ANN001
    from lib.config import get_settings

    monkeypatch.setenv("STRUCTURA_DETERMINISTIC_PLANNER", "true" if enabled else "false")
    get_settings.cache_clear()


def test_flag_on_gateway_failure_degrades_to_baseline(monkeypatch) -> None:  # noqa: ANN001
    from lib.config import get_settings

    _with_planner_flag(monkeypatch, True)
    try:
        source = _source([_table()])
        jobs = _RecordingJobs()
        result = _service_with(_FailingGateway(), source, jobs).annotate_document(
            source.document_id
        )
        manifest = result.manifest_result.manifest
        assert manifest.source_engine == "docling_baseline"
        assert manifest.review_required is True
        assert manifest.escalation_reason is not None
        assert manifest.escalation_reason.startswith("qwen_annotation_failed:")
        # the deterministic baseline still fans out extraction jobs
        assert jobs.created, "baseline regions must enqueue extraction jobs"
        assert all(job["job_type"] == "extract" for job in jobs.created)
    finally:
        get_settings.cache_clear()


def test_flag_off_gateway_failure_propagates(monkeypatch) -> None:  # noqa: ANN001
    import pytest

    from lib.config import get_settings
    from lib.model_runtime.http_client import ModelProtocolError

    _with_planner_flag(monkeypatch, False)
    try:
        source = _source([_table()])
        with pytest.raises(ModelProtocolError):
            _service_with(_FailingGateway(), source, _RecordingJobs()).annotate_document(
                source.document_id
            )
    finally:
        get_settings.cache_clear()


def test_flag_on_success_enforces_baseline_superset(monkeypatch) -> None:  # noqa: ANN001
    from lib.config import get_settings

    _with_planner_flag(monkeypatch, True)
    try:
        source = _source([_table()])
        jobs = _RecordingJobs()
        result = _service_with(_EmptyManifestGateway(), source, jobs).annotate_document(
            source.document_id
        )
        manifest = result.manifest_result.manifest
        telemetry = manifest.manifest.get("deterministic_baseline")
        assert isinstance(telemetry, dict)
        assert telemetry["baseline_region_count"] >= 1
        # the docling augmentation already unioned the baseline into the
        # empty Qwen plan, so the invariant verifies coverage without
        # needing to append anything
        assert telemetry["enforced_region_count"] == 0
        assert telemetry["plan_region_count"] >= telemetry["baseline_region_count"]
        assert manifest.regions, "baseline coverage present in the final plan"
        assert jobs.created
    finally:
        get_settings.cache_clear()
