from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def test_phase6_cli_dry_run_import_validates_pdf_without_importing(tmp_path: Path) -> None:
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    pdf = incoming / "import.pdf"
    pdf.write_bytes(b"%PDF-1.7\n%%EOF\n")
    old_timestamp = time.time() - 5
    os.utime(pdf, (old_timestamp, old_timestamp))

    result = subprocess.run(
        [
            sys.executable,
            "scripts/structura.py",
            "bulk-import",
            str(incoming),
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={
            **os.environ,
            "STRUCTURA_RUNTIME_ROOT": str(tmp_path / "runtime"),
        },
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["dryRun"] is True
    assert payload["acceptedPdfCount"] == 1
    assert payload["files"][0]["path"].endswith("import.pdf")
