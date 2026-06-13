from __future__ import annotations

from pathlib import Path


def test_model_output_wrapper_module_is_retired() -> None:
    repo_root = Path(__file__).parents[3]

    assert not (repo_root / "lib/extraction/model_output_wrappers.py").exists()
