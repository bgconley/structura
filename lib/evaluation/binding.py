"""Validate capture consistency before scoring any content."""

from __future__ import annotations

import hashlib
import math
from uuid import uuid5

from lib.document_parsing.model_output import PageParseOutput
from lib.document_parsing.normalization import normalize_page
from lib.evaluation.annotations import DocumentAnnotation
from lib.evaluation.captures import DocumentCapture
from lib.evaluation.identity import artifact_digest
from lib.evaluation.manifest import CaseBinding, EvaluationManifest


def validate_case(
    binding: CaseBinding,
    annotation: DocumentAnnotation,
    capture: DocumentCapture,
    manifest: EvaluationManifest,
) -> None:
    structure = capture.structure
    config = capture.configuration
    comparisons = (
        (binding.item_id, annotation.item_id),
        (binding.item_id, capture.item_id),
        (binding.annotation_sha256, artifact_digest(annotation)),
        (binding.capture_sha256, artifact_digest(capture)),
        (binding.original_sha256, annotation.original_sha256),
        (binding.original_sha256, structure.source.original_sha256),
        (binding.processing_run_id, structure.processing_run_id),
        (binding.parse_generation_id, structure.parse_generation_id),
        (binding.configuration_sha256, config.fingerprint),
        (capture.configuration_sha256, config.fingerprint),
        (binding.profile, config.profile),
        (binding.served_model, config.served_model),
        (binding.source_engine, config.source_engine),
        (binding.fixture_type, capture.fixture_type),
        (binding.origin_group, annotation.origin_group),
        (binding.template_group, annotation.template_group),
    )
    if any(expected != actual for expected, actual in comparisons):
        raise ValueError("Annotation/capture identity does not match frozen case binding.")
    if annotation.provenance.created_at > manifest.frozen_at:
        raise ValueError("Annotations must precede evaluation freeze.")
    if manifest.split == "blind_holdout" and (
        capture.fixture_type != "model_backed" or annotation.provenance.origin != "human_original"
    ):
        raise ValueError(
            "Blind holdout requires declared original-source human labels and live mode."
        )
    if len(annotation.pages) != len(structure.source.pages):
        raise ValueError("Annotation and capture source inventory differ.")
    _validate_raw_pages(capture, annotation)
    for chunk in structure.chunks:
        page = structure.pages[chunk.page_number - 1]
        origins = {
            element.text_origin for element in page.elements if element.id in chunk.element_ids
        }
        origins.update(
            cell.text_origin
            for table in page.tables
            if table.element_id in chunk.element_ids
            for cell in table.cells
        )
        if set(chunk.text_origins) != origins:
            raise ValueError("Chunk text attribution differs from its captured source elements.")


def _validate_raw_pages(capture: DocumentCapture, annotation: DocumentAnnotation) -> None:
    structure, config = capture.structure, capture.configuration
    raw = {item.page_number: item for item in capture.raw_pages}
    invocations = {item.page_numbers[0]: item for item in structure.invocations}
    if len(raw) != len(capture.raw_pages) or len(invocations) != len(structure.invocations):
        raise ValueError("Capture must contain one invocation/raw record per processed page.")
    if any(len(item.page_numbers) != 1 for item in structure.invocations):
        raise ValueError("This scorer supports the single-page neutral output contract only.")
    expected = {page.page_number for page in structure.pages if page.source is not None}
    if set(raw) != expected or set(invocations) != expected:
        raise ValueError("Every rendered parse page requires exact raw invocation records.")
    for page, gold in zip(structure.pages, annotation.pages, strict=True):
        if page.id != uuid5(structure.parse_generation_id, f"page:{page.page_number}"):
            raise ValueError("Page ID does not belong to captured parse generation.")
        if page.source is None:
            continue
        source = page.source
        invocation, output = invocations[page.page_number], raw[page.page_number]
        if (source.image_sha256, source.pixel_width, source.pixel_height) != (
            gold.image_sha256,
            gold.pixel_width,
            gold.pixel_height,
        ):
            raise ValueError("Capture does not use the annotated original-page render.")
        if (source.renderer, source.renderer_version) != (config.renderer, config.renderer_version):
            raise ValueError("Render configuration mismatch.")
        inventory = structure.source.pages[page.page_number - 1]
        scale = config.render_scale if inventory.unit == "pdf_canvas" else 1
        if (source.pixel_width, source.pixel_height) != (
            math.ceil(inventory.width * scale),
            math.ceil(inventory.height * scale),
        ):
            raise ValueError("Rendered dimensions disagree with source inventory/configuration.")
        if (
            invocation.request_id != output.request_id
            or invocation.raw_output_sha256
            != hashlib.sha256(output.raw_output.encode()).hexdigest()
            or invocation.profile != config.profile
            or invocation.served_model != config.served_model
            or invocation.source_engine != config.source_engine
            or invocation.prompt_version != config.prompt_version
            or invocation.output_schema_version != config.output_schema_version
            or config.output_schema_version != "structura.page_parse.v1"
        ):
            raise ValueError("Raw output/invocation/configuration identity mismatch.")
        rebuilt = normalize_page(
            PageParseOutput.model_validate_json(output.raw_output),
            source,
            structure.parse_generation_id,
        )
        if rebuilt != page:
            raise ValueError("Normalized page does not match its captured raw output.")
