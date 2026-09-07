"""Synthetic complete-content parser smoke; not a private-corpus quality gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.config import get_settings  # noqa: E402
from lib.document_parsing.document_parse import parse_document  # noqa: E402
from lib.document_parsing.qwen_page_parser import ParsedSourcePage  # noqa: E402
from lib.document_parsing.source_adapter import DocumentSource  # noqa: E402
from lib.model_runtime.ingestion_clients import ingestion_vision_client  # noqa: E402


def main() -> int:
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("--output-dir", type=Path, required=True)
    args = arguments.parse_args()
    args.output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    pages = []
    for lines in (
        [
            "REFERENCE LETTER",
            "Reference: LETTER-A123",
            "This is a complete searchable source document.",
            "Keep this text even when there are no invoice fields.",
            "Page 1 of 2",
        ],
        [
            "SYNTHETIC INVOICE",
            "Invoice: INV-902",
            "Description        Quantity        Amount",
            "Service                  1                  42.80",
            "Credit                     1                -12.35",
            "Total                                        30.45",
            "Page 2 of 2",
        ],
    ):
        image = Image.new("RGB", (1100, 650), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=32)
        for index, line in enumerate(lines):
            draw.text((35, 35 + index * 65), line, fill="black", font=font)
        pages.append(image)
    original = args.output_dir / "synthetic-source.tiff"
    pages[0].save(original, save_all=True, append_images=pages[1:])
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    settings = get_settings()
    checkpoints: list[ParsedSourcePage] = []
    with DocumentSource(
        original, asset_id=uuid4(), expected_sha256=digest, mime_type="image/tiff"
    ) as source:
        result = parse_document(
            source,
            ingestion_vision_client(settings),
            generation_id=uuid4(),
            run_id=uuid4(),
            assert_authority=lambda: None,
            checkpoint=checkpoints.append,
            timeout_seconds=settings.model_ingestion_timeout_seconds,
        )
        for number in range(1, len(source.inventory.pages) + 1):
            (args.output_dir / f"page-{number}.png").write_bytes(source.render(number).image_bytes)
    artifact = result.model_dump_json(indent=2).encode()
    (args.output_dir / "document-structure.json").write_bytes(artifact)
    for checkpoint in checkpoints:
        (args.output_dir / f"page-{checkpoint.page.page_number}-raw.json").write_text(
            checkpoint.raw_output
        )
    text_by_page = {
        number: "".join(chunk.text for chunk in result.chunks if chunk.page_number == number)
        for number in (1, 2)
    }
    expected = {
        1: ("LETTER-A123", "complete searchable source document", "no invoice fields"),
        2: ("INV-902", "42.80", "-12.35", "30.45"),
    }
    present = {
        str(number): all(value in text_by_page[number] for value in values)
        for number, values in expected.items()
    }
    passed = all(present.values()) and all(page.state == "processed" for page in result.pages)
    report = {
        "passed": passed,
        "fixture_type": "synthetic_model_backed_smoke",
        "source_sha256": digest,
        "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
        "page_count": len(result.pages),
        "request_count": len(result.invocations),
        "page_states": [page.state for page in result.pages],
        "expected_content_present": present,
        "element_count": sum(len(page.elements) for page in result.pages),
        "table_count": sum(len(page.tables) for page in result.pages),
        "chunk_count": len(result.chunks),
        "source_engines": sorted({call.source_engine for call in result.invocations}),
        "request_latency_ms": [call.latency_ms for call in result.invocations],
        "docling_imported": any(
            name == "docling" or name.startswith("docling.") for name in sys.modules
        ),
        "production_activated": False,
        "quality_gate": "not_evaluated",
    }
    (args.output_dir / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
