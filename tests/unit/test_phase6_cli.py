from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread


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


def test_phase6_cli_execute_requires_api_token(tmp_path: Path) -> None:
    incoming = tmp_path / "incoming"
    incoming.mkdir()

    result = subprocess.run(
        [
            sys.executable,
            "scripts/structura.py",
            "bulk-import",
            str(incoming),
            "--execute",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={
            **os.environ,
            "STRUCTURA_RUNTIME_ROOT": str(tmp_path / "runtime"),
        },
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "--api-token is required" in result.stderr


def test_phase6_cli_execute_posts_stable_pdfs_through_api(tmp_path: Path) -> None:
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    pdf = incoming / "execute.pdf"
    pdf.write_bytes(b"%PDF-1.7\n%%EOF\n")
    old_timestamp = time.time() - 5
    os.utime(pdf, (old_timestamp, old_timestamp))
    seen: list[dict[str, object]] = []

    class UploadHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = self.rfile.read(int(self.headers["Content-Length"]))
            seen.append(
                {
                    "path": self.path,
                    "token": self.headers.get("X-API-Token"),
                    "content_type": self.headers.get("Content-Type"),
                    "body": body,
                }
            )
            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"jobId":"11111111-1111-4111-8111-111111111111","status":"queued"}')

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), UploadHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/structura.py",
                "bulk-import",
                str(incoming),
                "--execute",
                "--api-base-url",
                f"http://127.0.0.1:{server.server_port}",
                "--api-token",
                "phase6-token",
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
    finally:
        server.shutdown()

    payload = json.loads(result.stdout)
    assert payload["dryRun"] is False
    assert payload["acceptedPdfCount"] == 1
    assert payload["executedPdfCount"] == 1
    assert payload["files"][0]["statusCode"] == 202
    assert seen[0]["path"] == "/api/v1/documents"
    assert seen[0]["token"] == "phase6-token"
    assert "multipart/form-data" in str(seen[0]["content_type"])
    assert b'name="source"' in seen[0]["body"]
    assert b"bulk_import" in seen[0]["body"]
    assert b'filename="execute.pdf"' in seen[0]["body"]
