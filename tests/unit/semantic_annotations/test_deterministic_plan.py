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


def _page_observation_source(
    *,
    family: str,
    title: str,
    page_texts: list[str],
) -> ExtractionSourceDocument:
    pages = [
        ParsedPageText(
            page_id=uuid4(),
            page_number=index,
            text=text,
            has_text_layer=True,
        )
        for index, text in enumerate(page_texts, start=1)
    ]
    elements = [
        ParsedElementText(
            element_id=uuid4(),
            page_number=page.page_number,
            ordinal=page.page_number,
            text=page.text,
        )
        for page in pages
    ]
    return ExtractionSourceDocument(
        document_id=uuid4(),
        household_id=uuid4(),
        title=title,
        original_filename=f"{title}.pdf",
        mime_type="application/pdf",
        family=family,
        subtype=None,
        sensitivity="standard",
        document_date=date(2026, 6, 1),
        counterparty_display=None,
        primary_folder_id=None,
        metadata={},
        pages=pages,
        elements=elements,
        tables=[],
    )


def _manifest_like_baseline_with_regions(
    baseline,
    regions: list[SemanticRegionAnnotation],
):
    return baseline.__class__(
        document_id=baseline.document_id,
        household_id=baseline.household_id,
        quality_mode=baseline.quality_mode,
        profile_name="qwen",
        source_engine="qwen3_vl_8b",
        model_name="qwen",
        model_version="t",
        prompt_version="t",
        pages=baseline.pages,
        regions=regions,
        confidence={},
        manifest={"regions": [], "pages": []},
    )


def test_baseline_manifest_plans_tables_without_a_model() -> None:
    source = _source([_table()])
    baseline = deterministic_baseline_manifest(source)
    assert baseline.source_engine == "docling"
    assert baseline.model_name == "deterministic-planner"
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
    baseline_region = baseline.regions[0]
    qwen_region = SemanticRegionAnnotation(
        semantic_type=baseline_region.semantic_type,
        priority=baseline_region.priority,
        granite_task=baseline_region.granite_task,
        grounding=SemanticGroundingRef(kind="table", table_id=source.tables[0].table_id),
        target_schema=baseline_region.target_schema,
        expected_fields=baseline_region.expected_fields,
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


def test_table_region_wrong_semantic_type_does_not_cover_baseline_table_target() -> None:
    source = _source([_table()])
    baseline = deterministic_baseline_manifest(source)
    wrong_table_region = SemanticRegionAnnotation(
        semantic_type="receipt_line_item_table",
        priority="critical",
        granite_task="tables_json",
        grounding=SemanticGroundingRef(kind="table", table_id=source.tables[0].table_id),
        target_schema="receipt",
        expected_fields=("item_description", "quantity", "unit_price", "line_total"),
    )
    plan = SemanticAnnotationResult(
        manifest=_manifest_like_baseline_with_regions(baseline, [wrong_table_region])
    )

    enforced = apply_baseline_invariant(source, baseline, plan)

    telemetry = enforced.manifest.manifest["deterministic_baseline"]
    assert telemetry["enforced_region_count"] == 1
    assert {
        (region.semantic_type, region.target_schema) for region in enforced.manifest.regions
    } == {
        ("receipt_line_item_table", "receipt"),
        (baseline.regions[0].semantic_type, baseline.regions[0].target_schema),
    }


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
        assert manifest.source_engine == "docling"
        assert manifest.model_name == "deterministic-planner"
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


def test_table_grounded_kvp_region_does_not_cover_baseline_table_target() -> None:
    # 2026-06-10 E3 review: a Qwen billing_summary kvp region sharing the
    # table grounding must not suppress the deterministic tables_json target.
    source = _source([_table()])
    baseline = deterministic_baseline_manifest(source)
    kvp_region = SemanticRegionAnnotation(
        semantic_type="billing_summary",
        priority="high",
        granite_task="kvp",
        grounding=SemanticGroundingRef(kind="table", table_id=source.tables[0].table_id),
        target_schema="invoice",
        expected_fields=("total",),
    )
    plan = SemanticAnnotationResult(
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
            regions=[kvp_region],
            confidence={},
            manifest={"regions": [], "pages": []},
        )
    )
    enforced = apply_baseline_invariant(source, baseline, plan)
    telemetry = enforced.manifest.manifest["deterministic_baseline"]
    assert telemetry["enforced_region_count"] == len(baseline.regions)
    tasks = {(region.semantic_type, region.granite_task) for region in enforced.manifest.regions}
    assert ("billing_summary", "kvp") in tasks
    assert any(task == "tables_json" for _stype, task in tasks)


def test_wrong_page_escrow_region_does_not_cover_baseline_escrow_target() -> None:
    source = _page_observation_source(
        family="mortgage_escrow_statement",
        title="UWM Final Escrow Statement",
        page_texts=[
            "Cover page with general servicing notes.",
            "Escrow mortgage shortage surplus details and monthly payment.",
        ],
    )
    baseline = deterministic_baseline_manifest(source)
    baseline_region = next(
        region for region in baseline.regions if region.semantic_type == "escrow_summary"
    )
    qwen_region = SemanticRegionAnnotation(
        semantic_type="escrow_summary",
        priority="high",
        granite_task="kvp",
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
        target_schema="document_observation",
        expected_fields=baseline_region.expected_fields,
    )
    plan = SemanticAnnotationResult(
        manifest=_manifest_like_baseline_with_regions(baseline, [qwen_region])
    )

    enforced = apply_baseline_invariant(source, baseline, plan)

    telemetry = enforced.manifest.manifest["deterministic_baseline"]
    assert telemetry["enforced_region_count"] == 1
    assert {region.grounding.page_id for region in enforced.manifest.regions} == {
        source.pages[0].page_id,
        source.pages[1].page_id,
    }


def test_wrong_page_seller_region_does_not_cover_baseline_seller_target() -> None:
    source = _page_observation_source(
        family="real_estate_title",
        title="Real Estate Title Closing Packet",
        page_texts=[
            "Introductory page with recording notes.",
            "Seller information title company closing settlement proceeds.",
        ],
    )
    baseline = deterministic_baseline_manifest(source)
    baseline_region = next(
        region for region in baseline.regions if region.semantic_type == "seller_information_block"
    )
    qwen_region = SemanticRegionAnnotation(
        semantic_type="seller_information_block",
        priority="high",
        granite_task="kvp",
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
        target_schema="document_observation",
        expected_fields=baseline_region.expected_fields,
    )
    plan = SemanticAnnotationResult(
        manifest=_manifest_like_baseline_with_regions(baseline, [qwen_region])
    )

    enforced = apply_baseline_invariant(source, baseline, plan)

    telemetry = enforced.manifest.manifest["deterministic_baseline"]
    assert telemetry["enforced_region_count"] == 1
    assert {region.grounding.page_id for region in enforced.manifest.regions} == {
        source.pages[0].page_id,
        source.pages[1].page_id,
    }


def test_wrong_page_generic_kvp_region_does_not_cover_baseline_target() -> None:
    source = _page_observation_source(
        family="generic",
        title="Generic form",
        page_texts=["Intro page", "Important form fields and visible values."],
    )
    baseline = deterministic_baseline_manifest(source)
    baseline_region = SemanticRegionAnnotation(
        semantic_type="generic_form_kvp",
        priority="high",
        granite_task="kvp",
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[1].page_id),
        target_schema="document_observation",
        expected_fields=("field_labels", "visible_values"),
    )
    baseline = _manifest_like_baseline_with_regions(baseline, [baseline_region])
    qwen_region = SemanticRegionAnnotation(
        semantic_type="generic_form_kvp",
        priority="high",
        granite_task="kvp",
        grounding=SemanticGroundingRef(kind="page", page_id=source.pages[0].page_id),
        target_schema="document_observation",
        expected_fields=baseline_region.expected_fields,
    )
    plan = SemanticAnnotationResult(
        manifest=_manifest_like_baseline_with_regions(baseline, [qwen_region])
    )

    enforced = apply_baseline_invariant(source, baseline, plan)

    telemetry = enforced.manifest.manifest["deterministic_baseline"]
    assert telemetry["enforced_region_count"] == 1
    assert {region.grounding.page_id for region in enforced.manifest.regions} == {
        source.pages[0].page_id,
        source.pages[1].page_id,
    }


def test_same_page_observation_region_covers_baseline_target() -> None:
    source = _page_observation_source(
        family="mortgage_escrow_statement",
        title="UWM Final Escrow Statement",
        page_texts=[
            "Cover page with general servicing notes.",
            "Escrow mortgage shortage surplus details and monthly payment.",
        ],
    )
    baseline = deterministic_baseline_manifest(source)
    baseline_region = next(
        region for region in baseline.regions if region.semantic_type == "escrow_summary"
    )
    qwen_region = SemanticRegionAnnotation(
        semantic_type="escrow_summary",
        priority="high",
        granite_task="kvp",
        grounding=baseline_region.grounding,
        target_schema=baseline_region.target_schema,
        expected_fields=baseline_region.expected_fields,
    )
    plan = SemanticAnnotationResult(
        manifest=_manifest_like_baseline_with_regions(baseline, [qwen_region])
    )

    enforced = apply_baseline_invariant(source, baseline, plan)

    telemetry = enforced.manifest.manifest["deterministic_baseline"]
    assert telemetry["enforced_region_count"] == 0
    assert enforced.manifest.regions == [qwen_region]


def test_baseline_manifest_uses_active_profile_when_supplied() -> None:
    source = _source([_table()])
    baseline = deterministic_baseline_manifest(source, profile_name="qwen3-vl-8b-fp8-semantic:v1")
    assert baseline.profile_name == "qwen3-vl-8b-fp8-semantic:v1"
    assert baseline.source_engine == "docling"


def test_flag_on_transient_failure_propagates_for_job_retry(monkeypatch) -> None:  # noqa: ANN001
    import pytest

    from lib.config import get_settings
    from lib.model_runtime.http_client import ModelTimeoutError

    class _TimeoutGateway:
        def annotate(self, source, *, quality_mode):  # noqa: ANN001, ANN003
            raise ModelTimeoutError("qwen timed out")

    _with_planner_flag(monkeypatch, True)
    try:
        source = _source([_table()])
        with pytest.raises(ModelTimeoutError):
            _service_with(_TimeoutGateway(), source, _RecordingJobs()).annotate_document(
                source.document_id
            )
    finally:
        get_settings.cache_clear()
