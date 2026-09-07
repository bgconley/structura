"""Frozen synthetic source loading and canonical checkout/runtime guards."""

from __future__ import annotations

import hashlib
import json
import subprocess  # nosec B404
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from lib.config import Settings
from lib.evaluation.annotations import DocumentAnnotation
from lib.model_runtime.profiles import QWEN_INGESTION_PROFILE
from scripts.gpu.page_understanding_probe.fixture_authoring import original_bytes
from scripts.gpu.probe_database import verify_isolated_database

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests/fixtures/page_understanding_probe"
_PROBE_FILES = (
    "scripts/gpu/probe_page_understanding.py",
    *(
        f"scripts/gpu/page_understanding_probe/{name}.py"
        for name in (
            "__init__",
            "inputs",
            "execution",
            "capture",
            "scoring",
            "observations",
            "fixture_authoring",
        )
    ),
    *(
        f"tests/fixtures/page_understanding_probe/{name}"
        for name in (
            "page-1.png",
            "page-2.png",
            "page-3.png",
            "annotation.json",
            "expectations.json",
            "source-recipe.json",
        )
    ),
)


@dataclass(frozen=True)
class ProbeInputs:
    original: bytes
    annotation: DocumentAnnotation
    expectations: dict[str, Any]


def load_inputs(directory: Path = FIXTURE) -> ProbeInputs:
    annotation = DocumentAnnotation.model_validate_json(
        _read(directory / "annotation.json", 512 * 1024)
    )
    expected = json.loads(_read(directory / "expectations.json", 512 * 1024))
    recipe = _read(directory / "source-recipe.json", 128 * 1024)
    if (
        len(annotation.pages) != 3
        or [p["family"] for p in expected["pages"]] != ["invoice", "receipt", "medical_eob"]
        or [p["page_number"] for p in expected["pages"]] != [1, 2, 3]
        or expected["source_recipe_sha256"] != hashlib.sha256(recipe).hexdigest()
    ):
        raise RuntimeError("Synthetic source inventory or authored expectation binding differs.")
    images = []
    try:
        for page in annotation.pages:
            path = directory / f"page-{page.page_number}.png"
            data = _read(path, 10 * 1024 * 1024)
            if hashlib.sha256(data).hexdigest() != page.image_sha256:
                raise RuntimeError("Synthetic reference PNG differs from its authored annotation.")
            with Image.open(BytesIO(data)) as image:
                if image.mode != "RGB" or image.size != (page.pixel_width, page.pixel_height):
                    raise RuntimeError("Synthetic reference pixels differ from their annotation.")
                image.load()
                # Raw TIFF recipe is grayscale; no color may silently disappear.
                gray = image.convert("L").convert("RGB")
                if gray.tobytes() != image.tobytes():
                    raise RuntimeError("Synthetic grayscale source would change reference pixels.")
                images.append(gray)
        original = original_bytes(images)
    finally:
        for rendered_image in images:
            rendered_image.close()
    if (
        len(original) != expected["original_byte_size"]
        or hashlib.sha256(original).hexdigest() != expected["original_sha256"]
        or expected["original_sha256"] != annotation.original_sha256
    ):
        raise RuntimeError("Rebuilt original differs from its frozen TIFF bytes.")
    return ProbeInputs(original, annotation, expected)


def preflight(settings: Settings, output: Path, expected_commit: str) -> str:
    if (
        settings.model_mode not in {"live", "required"}
        or settings.model_ingestion_profile != QWEN_INGESTION_PROFILE
    ):
        raise RuntimeError("Probe requires live mode and the exact accepted ingestion profile.")
    if (
        settings.runtime_root.resolve() != output.resolve()
        or settings.canonical_objects_root.resolve() != (output / "objects/canonical").resolve()
        or settings.derived_objects_root.resolve() != (output / "objects/derived").resolve()
        or output.exists()
    ):
        raise RuntimeError("Probe requires a fresh isolated runtime and exact object roots.")
    # Fixed commands only. No arbitrary command/path interpolation or shell execution.
    commit = subprocess.check_output(  # nosec B603
        ["/usr/bin/git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=5
    ).strip()
    clean = (
        subprocess.run(  # nosec B603
            ["/usr/bin/git", "diff", "--quiet", "HEAD"], cwd=ROOT, timeout=5, check=False
        ).returncode
        == 0
    )
    if commit != expected_commit or not clean:
        raise RuntimeError("Probe source checkout differs from the declared clean commit.")
    tracked = subprocess.run(  # nosec B603
        ["/usr/bin/git", "ls-files", "--error-unmatch", "--", *_PROBE_FILES],
        cwd=ROOT,
        timeout=5,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if tracked.returncode != 0:
        raise RuntimeError("Probe code and source artifacts must belong to the declared commit.")
    verify_isolated_database(settings.database_url)
    return commit


def _read(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        value = stream.read(limit + 1)
    if len(value) > limit:
        raise RuntimeError("Synthetic probe input exceeds its bound.")
    return value
