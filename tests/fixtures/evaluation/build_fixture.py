"""Rebuild explicitly synthetic reference images and independently authored labels/output."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from uuid import UUID, uuid5

from PIL import Image, ImageDraw

from lib.document_parsing.model_output import PageParseOutput
from lib.document_parsing.normalization import normalize_page
from lib.document_parsing.searchable_text import page_chunks
from lib.document_parsing.structure import (
    DocumentStructure,
    ParseInvocation,
    SourceInventory,
    SourcePage,
    SourceRender,
)
from lib.document_processing.models import ParseConfiguration
from lib.evaluation.annotations import DocumentAnnotation
from lib.evaluation.captures import CapturedRawPage, DocumentCapture
from lib.evaluation.identity import artifact_digest
from lib.evaluation.manifest import CaseBinding, EvaluationManifest

HERE = Path(__file__).parent
NAMESPACE = UUID("fb25fafd-8510-459c-96b9-f377a0451cb9")


def write_json(name: str, payload: object) -> None:
    (HERE / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def box(left: float, top: float, right: float, bottom: float) -> dict[str, float]:
    return dict(left=left, top=top, right=right, bottom=bottom)


def model_box(left: float, top: float, right: float, bottom: float) -> dict[str, float]:
    return box(left * 1000 / 600, top * 1000 / 800, right * 1000 / 600, bottom * 1000 / 800)


def main() -> None:
    images = [Image.new("RGB", (600, 800), "white") for _ in range(2)]
    first, second = (ImageDraw.Draw(image) for image in images)
    for position, text in [
        ((30, 30), "Invoice INV-001"),
        ((30, 100), "Copy"),
        ((30, 140), "Copy"),
        ((35, 205), "Item"),
        ((185, 205), "Amount"),
        ((35, 245), "Service"),
        ((185, 245), "12.50"),
    ]:
        first.text(position, text, fill="black")
    for bounds in (
        (30, 200, 180, 240),
        (180, 200, 330, 240),
        (30, 240, 180, 280),
        (180, 240, 330, 280),
    ):
        first.rectangle(bounds, outline="black")
    second.text((30, 30), "Terms", fill="black")
    second.text((30, 100), "Payment due 2026-09-30.", fill="black")
    images[0].save(
        HERE / "original.tiff", save_all=True, append_images=images[1:], compression="tiff_deflate"
    )
    original = (HERE / "original.tiff").read_bytes()
    original_hash = hashlib.sha256(original).hexdigest()
    sources = []
    for number, image in enumerate(images, 1):
        data = io.BytesIO()
        image.save(data, format="PNG")
        (HERE / f"page-{number}.png").write_bytes(data.getvalue())
        sources.append(
            SourceRender(
                page_number=number,
                image_sha256=hashlib.sha256(data.getvalue()).hexdigest(),
                pixel_width=600,
                pixel_height=800,
                renderer="synthetic-reference",
                renderer_version="v1",
            )
        )
    # Gold labels are authored from the reference content, not from normalized output.
    gold_pages = [
        dict(
            page_number=1,
            image_sha256=sources[0].image_sha256,
            pixel_width=600,
            pixel_height=800,
            regions=[
                dict(
                    id="title",
                    kind="heading",
                    readability="readable",
                    text="Invoice INV-001",
                    bbox=box(30, 30, 250, 70),
                ),
                dict(
                    id="copy-a",
                    kind="paragraph",
                    readability="readable",
                    text="Copy",
                    bbox=box(30, 100, 150, 120),
                ),
                dict(
                    id="copy-b",
                    kind="paragraph",
                    readability="readable",
                    text="Copy",
                    bbox=box(30, 140, 150, 160),
                ),
                dict(
                    id="charges",
                    kind="table",
                    readability="readable",
                    text="",
                    bbox=box(30, 200, 330, 280),
                ),
            ],
            tables=[
                dict(
                    region_id="charges",
                    row_count=2,
                    column_count=2,
                    continuation_group=None,
                    cells=[
                        dict(
                            row=0,
                            column=0,
                            row_span=1,
                            column_span=1,
                            text="Item",
                            readability="readable",
                        ),
                        dict(
                            row=0,
                            column=1,
                            row_span=1,
                            column_span=1,
                            text="Amount",
                            readability="readable",
                        ),
                        dict(
                            row=1,
                            column=0,
                            row_span=1,
                            column_span=1,
                            text="Service",
                            readability="readable",
                        ),
                        dict(
                            row=1,
                            column=1,
                            row_span=1,
                            column_span=1,
                            text="12.50",
                            readability="readable",
                        ),
                    ],
                )
            ],
            reading_order_pairs=[["title", "copy-a"], ["copy-a", "copy-b"], ["copy-b", "charges"]],
            sensitive_text=[
                dict(text="INV-001", kind="identifier", occurrences=1),
                dict(text="12.50", kind="amount", occurrences=1),
            ],
        ),
        dict(
            page_number=2,
            image_sha256=sources[1].image_sha256,
            pixel_width=600,
            pixel_height=800,
            regions=[
                dict(
                    id="terms",
                    kind="heading",
                    readability="readable",
                    text="Terms",
                    bbox=box(30, 30, 250, 70),
                ),
                dict(
                    id="due",
                    kind="paragraph",
                    readability="readable",
                    text="Payment due 2026-09-30.",
                    bbox=box(30, 100, 350, 130),
                ),
            ],
            tables=[],
            reading_order_pairs=[["terms", "due"]],
            sensitive_text=[dict(text="2026-09-30", kind="date", occurrences=1)],
        ),
    ]
    annotation = DocumentAnnotation.model_validate(
        dict(
            item_id="synthetic-invoice",
            original_sha256=original_hash,
            family_labels=["invoice"],
            modality="image",
            origin_group="synthetic-origin-v1",
            template_group="synthetic-template-v1",
            provenance=dict(
                origin="synthetic_author",
                annotation_revision="v1",
                author_reference="fixture-author",
                adjudicator_reference=None,
                created_at="2026-09-01T00:00:00Z",
                source_only=True,
            ),
            pages=gold_pages,
        )
    )
    # Separate hand-authored fake model outputs. No live model or human review is claimed.
    output_pages = [
        dict(
            page_number=1,
            state="processed",
            diagnostics=[],
            elements=[
                dict(
                    kind="heading",
                    text="Invoice INV-001",
                    bbox=model_box(30, 30, 250, 70),
                    parent_index=None,
                    table=None,
                ),
                dict(
                    kind="paragraph",
                    text="Copy",
                    bbox=model_box(30, 100, 150, 120),
                    parent_index=None,
                    table=None,
                ),
                dict(
                    kind="paragraph",
                    text="Copy",
                    bbox=model_box(30, 140, 150, 160),
                    parent_index=None,
                    table=None,
                ),
                dict(
                    kind="table",
                    text="",
                    bbox=model_box(30, 200, 330, 280),
                    parent_index=None,
                    table=dict(
                        row_count=2,
                        column_count=2,
                        continuation_key=None,
                        cells=[
                            dict(
                                row=0,
                                column=0,
                                row_span=1,
                                column_span=1,
                                text="Item",
                                is_header=True,
                                bbox=model_box(30, 200, 180, 240),
                            ),
                            dict(
                                row=0,
                                column=1,
                                row_span=1,
                                column_span=1,
                                text="Amount",
                                is_header=True,
                                bbox=model_box(180, 200, 330, 240),
                            ),
                            dict(
                                row=1,
                                column=0,
                                row_span=1,
                                column_span=1,
                                text="Service",
                                is_header=False,
                                bbox=model_box(30, 240, 180, 280),
                            ),
                            dict(
                                row=1,
                                column=1,
                                row_span=1,
                                column_span=1,
                                text="12.50",
                                is_header=False,
                                bbox=model_box(180, 240, 330, 280),
                            ),
                        ],
                    ),
                ),
            ],
        ),
        dict(
            page_number=2,
            state="processed",
            diagnostics=[],
            elements=[
                dict(
                    kind="heading",
                    text="Terms",
                    bbox=model_box(30, 30, 250, 70),
                    parent_index=None,
                    table=None,
                ),
                dict(
                    kind="paragraph",
                    text="Payment due 2026-09-30.",
                    bbox=model_box(30, 100, 350, 130),
                    parent_index=None,
                    table=None,
                ),
            ],
        ),
    ]
    config = ParseConfiguration(
        profile="synthetic-parse-fixture:v1",
        served_model="synthetic-fixture",
        source_engine="synthetic-fixture",
        model_revision="v1",
        prompt_version="synthetic-v1",
        output_schema_version="structura.page_parse.v1",
        normalizer_version="v1",
        chunker_version="v1",
        renderer="synthetic-reference",
        renderer_version="v1",
        render_scale=1,
    )
    generation_id, run_id = uuid5(NAMESPACE, "parse"), uuid5(NAMESPACE, "run")
    pages, invocations, raw_pages = [], [], []
    for output, source in zip(output_pages, sources, strict=True):
        raw = json.dumps(output, sort_keys=True)
        pages.append(normalize_page(PageParseOutput.model_validate(output), source, generation_id))
        invocation = ParseInvocation(
            request_id=uuid5(NAMESPACE, f"call-{source.page_number}"),
            page_numbers=(source.page_number,),
            profile=config.profile,
            served_model=config.served_model,
            source_engine=config.source_engine,
            prompt_version=config.prompt_version,
            output_schema_version=config.output_schema_version,
            raw_output_sha256=hashlib.sha256(raw.encode()).hexdigest(),
            finish_reason="stop",
            latency_ms=0,
        )
        invocations.append(invocation)
        raw_pages.append(
            CapturedRawPage(
                request_id=invocation.request_id, page_number=source.page_number, raw_output=raw
            )
        )
    capture = DocumentCapture(
        item_id=annotation.item_id,
        fixture_type="deterministic_fixture",
        model_mode="fixture",
        commit="0" * 40,
        configuration=config,
        configuration_sha256=config.fingerprint,
        max_output_tokens=8192,
        temperature=0,
        structure=DocumentStructure(
            parse_generation_id=generation_id,
            processing_run_id=run_id,
            source=SourceInventory(
                original_asset_id=uuid5(NAMESPACE, "original"),
                original_sha256=original_hash,
                mime_type="image/tiff",
                byte_size=len(original),
                pages=tuple(
                    SourcePage(page_number=n, width=600, height=800, unit="pixels") for n in (1, 2)
                ),
            ),
            pages=tuple(pages),
            invocations=tuple(invocations),
            chunks=tuple(chunk for page in pages for chunk in page_chunks(page, generation_id)),
        ),
        raw_pages=tuple(raw_pages),
    )
    manifest = EvaluationManifest(
        evaluation_id=uuid5(NAMESPACE, "evaluation"),
        frozen_at="2026-09-02T00:00:00Z",
        split="synthetic_regression",
        split_revision="v1",
        exposures=(),
        development_origin_groups=(),
        development_template_groups=(),
        cases=(
            CaseBinding(
                item_id=annotation.item_id,
                annotation_sha256=artifact_digest(annotation),
                capture_sha256=artifact_digest(capture),
                original_sha256=original_hash,
                processing_run_id=run_id,
                parse_generation_id=generation_id,
                configuration_sha256=config.fingerprint,
                profile=config.profile,
                served_model=config.served_model,
                source_engine=config.source_engine,
                fixture_type="deterministic_fixture",
                origin_group=annotation.origin_group,
                template_group=annotation.template_group,
            ),
        ),
    )
    write_json("annotation.json", annotation.model_dump(mode="json"))
    write_json("capture.json", capture.model_dump(mode="json"))
    write_json("manifest.json", manifest.model_dump(mode="json"))
    (HERE / "manifest.sha256").write_text(artifact_digest(manifest) + "\n")


if __name__ == "__main__":
    main()
