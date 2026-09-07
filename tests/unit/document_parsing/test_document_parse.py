from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from uuid import uuid4

import pytest
from PIL import Image

from lib.document_parsing.document_parse import parse_document
from lib.document_parsing.source_adapter import DocumentSource
from lib.model_runtime.contracts import VisionGenerateResponse
from lib.model_runtime.http_client import ModelServiceError


class SyntheticClient:
    def __init__(self, *, after_generate=lambda: None):
        self.calls = []
        self.after_generate = after_generate

    def generate(self, request):
        self.calls.append(request)
        # Distinct typed table and prose content, exceeding one chunk's budget.
        number = int(request.prompt.split("Parse page ")[1].split(" ")[0])
        data = {
            "page_number": number,
            "state": "processed",
            "diagnostics": [],
            "elements": [
                {
                    "kind": "paragraph",
                    "text": f"Page {number}: " + "Exact A-001 42.80. " * 250,
                    "bbox": {"left": 0, "top": 0, "right": 900, "bottom": 500},
                    "parent_index": None,
                    "table": None,
                },
                {
                    "kind": "table",
                    "text": "Charges",
                    "bbox": {"left": 0, "top": 500, "right": 1000, "bottom": 1000},
                    "parent_index": None,
                    "table": {
                        "row_count": 1,
                        "column_count": 2,
                        "continuation_key": None,
                        "cells": [
                            {
                                "row": 0,
                                "column": 0,
                                "row_span": 1,
                                "column_span": 1,
                                "text": "Credit",
                                "is_header": False,
                                "bbox": {"left": 0, "top": 500, "right": 500, "bottom": 1000},
                            },
                            {
                                "row": 0,
                                "column": 1,
                                "row_span": 1,
                                "column_span": 1,
                                "text": "-12.35",
                                "is_header": False,
                                "bbox": {"left": 500, "top": 500, "right": 1000, "bottom": 1000},
                            },
                        ],
                    },
                },
            ],
        }
        self.after_generate()
        return VisionGenerateResponse(
            profile_name=request.profile_name,
            model_name="qwen38-27b-bf16-oxcart",
            model_version="synthetic-test-fixture",
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


def document_source(tmp_path):
    path = tmp_path / "synthetic.tiff"
    a, b = Image.new("RGB", (100, 100), "red"), Image.new("RGB", (100, 100), "blue")
    a.save(path, save_all=True, append_images=[b])
    return DocumentSource(
        path,
        asset_id=uuid4(),
        expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        mime_type="image/tiff",
    )


def test_partial_budget_is_explicit_and_resume_preserves_ids_and_all_content(tmp_path):
    checkpoints = []
    client = SyntheticClient()
    generation, run = uuid4(), uuid4()
    with document_source(tmp_path) as source:
        first = parse_document(
            source,
            client,
            generation_id=generation,
            run_id=run,
            max_new_pages=1,
            assert_authority=lambda: None,
            checkpoint=checkpoints.append,
        )
        assert [page.state for page in first.pages] == ["processed", "deferred"]
        assert len(checkpoints) == len(client.calls) == 1
        assert first.pages[1].source is None
        second = parse_document(
            source,
            client,
            generation_id=generation,
            run_id=run,
            completed=tuple(checkpoints),
            assert_authority=lambda: None,
            checkpoint=checkpoints.append,
        )
        assert [page.state for page in second.pages] == ["processed", "processed"]
        assert second.pages[0] == first.pages[0]
        assert len(client.calls) == 2
        for page in second.pages:
            chunks = [chunk for chunk in second.chunks if chunk.page_number == page.page_number]
            text = "".join(chunk.text for chunk in chunks)
            assert text == page.elements[0].text + "Charges\nCredit\t-12.35"
            assert all(chunk.text_origins == ("model_transcription",) for chunk in chunks)
        with pytest.raises(ValueError, match="another generation"):
            parse_document(
                source,
                client,
                generation_id=uuid4(),
                run_id=run,
                completed=checkpoints,
                assert_authority=lambda: None,
                checkpoint=lambda _: None,
            )


def test_lost_authority_after_inference_never_checkpoints_or_calls_next_page(tmp_path):
    cancelled = False
    checkpoints = []

    def cancel():
        nonlocal cancelled
        cancelled = True

    def authority():
        if cancelled:
            raise RuntimeError("lost current run")

    client = SyntheticClient(after_generate=cancel)
    with document_source(tmp_path) as source, pytest.raises(RuntimeError, match="lost current run"):
        parse_document(
            source,
            client,
            generation_id=uuid4(),
            run_id=uuid4(),
            assert_authority=authority,
            checkpoint=checkpoints.append,
        )
    assert not checkpoints and len(client.calls) == 1


def test_model_failure_preserves_only_completed_checkpoints_for_retry(tmp_path):
    checkpoints = []

    class FailingSecondPage(SyntheticClient):
        def generate(self, request):
            if len(self.calls) == 1:
                raise ModelServiceError("synthetic outage")
            return super().generate(request)

    with document_source(tmp_path) as source, pytest.raises(ModelServiceError):
        parse_document(
            source,
            FailingSecondPage(),
            generation_id=uuid4(),
            run_id=uuid4(),
            assert_authority=lambda: None,
            checkpoint=checkpoints.append,
        )
    assert len(checkpoints) == 1


def test_wrong_source_response_does_not_create_structure(tmp_path):
    class WrongImage(SyntheticClient):
        def generate(self, request):
            return replace(super().generate(request), input_sha256=("0" * 64,))

    with document_source(tmp_path) as source, pytest.raises(ValueError, match="exact source image"):
        parse_document(
            source,
            WrongImage(),
            generation_id=uuid4(),
            run_id=uuid4(),
            assert_authority=lambda: None,
            checkpoint=lambda _: pytest.fail("invalid publication"),
        )
