from __future__ import annotations

import re
from pathlib import Path

MAKEFILE = Path("Makefile")


def test_release_readiness_requires_model_backed_model_corpus() -> None:
    content = MAKEFILE.read_text(encoding="utf-8")

    assert "model-corpus-release:" in content
    assert re.search(r"^model-corpus-release:\n\t.*--require-model-backed", content, re.M)
    assert re.search(r"^release-readiness: .*model-corpus-release", content, re.M)


def test_shape_model_corpus_uses_deterministic_example_manifest() -> None:
    content = MAKEFILE.read_text(encoding="utf-8")

    assert re.search(
        r"^MODEL_CORPUS_SHAPE_MANIFEST \?= .*phase8_5_model_manifest\.example\.json",
        content,
        re.M,
    )
    assert re.search(
        r"^model-corpus:\n\t.*\$\(MODEL_CORPUS_SHAPE_MANIFEST\)",
        content,
        re.M,
    )


def test_makefile_exposes_model_corpus_manifest_builder() -> None:
    content = MAKEFILE.read_text(encoding="utf-8")

    assert "build-model-corpus-manifest:" in content
    assert "scripts/build_model_corpus_manifest.py" in content
