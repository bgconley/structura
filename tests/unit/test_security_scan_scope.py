from __future__ import annotations

from pathlib import Path


def test_semgrep_scope_excludes_generated_artifacts() -> None:
    ignore_file = Path(".semgrepignore")

    assert ignore_file.exists()
    entries = {
        line.strip()
        for line in ignore_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "artifacts/" in entries
