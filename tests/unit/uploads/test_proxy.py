"""Actual Node proxy process, actual HTTP sockets and a deliberately simple upstream."""

from __future__ import annotations

import http.client
import os
import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


class Upstream(BaseHTTPRequestHandler):
    def do_POST(self):
        received = 0
        if self.headers.get("Transfer-Encoding") == "chunked":
            while True:
                line = self.rfile.readline()
                if not line:
                    return
                count = int(line.strip(), 16)
                if count == 0:
                    self.rfile.readline()
                    break
                received += len(self.rfile.read(count))
                self.rfile.read(2)
        else:
            received = len(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        body = str(received).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    do_PUT = do_POST

    def log_message(self, *_args):
        pass


@pytest.fixture
def proxy():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for the actual web proxy test")
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    root = Path(__file__).resolve().parents[3]
    env = dict(
        os.environ,
        PORT=str(port),
        STRUCTURA_PROXY_MAX_BODY_BYTES="32768",
        STRUCTURA_API_UPSTREAM=f"http://127.0.0.1:{upstream.server_port}",
    )
    process = subprocess.Popen(
        [node, "apps/web/server.mjs"],
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 5
        while True:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    pytest.fail("Proxy did not start")
                time.sleep(0.02)
        yield port
    finally:
        process.terminate()
        process.wait(timeout=5)
        upstream.shutdown()
        upstream.server_close()
        thread.join(5)


def transfer(port, path, chunks, *, method="POST", declared=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {} if declared is None else {"Content-Length": str(declared)}
    try:
        connection.request(
            method, path, body=iter(chunks), headers=headers, encode_chunked=declared is None
        )
        result = connection.getresponse()
        return result.status, result.read()
    finally:
        connection.close()


@pytest.mark.parametrize("declared", [None, 32768])
def test_actual_proxy_accepts_exact_file_limit_with_or_without_declared_length(proxy, declared):
    assert transfer(
        proxy, "/api/v1/uploads/id/content", [b"a" * 32768], method="PUT", declared=declared
    ) == (200, b"32768")


def test_actual_proxy_rejects_chunked_body_over_limit(proxy):
    status, body = transfer(proxy, "/api/v1/uploads/id/content", [b"a" * 16384] * 3, method="PUT")
    assert status == 413
    assert b"proxy limit" in body


def test_new_controls_are_bounded_without_changing_other_api_limits(proxy):
    assert transfer(proxy, "/api/v1/uploads", [b"a" * 16385])[0] == 413
    assert transfer(proxy, "/api/v1/uploads/id/decision", [b"a" * 16385])[0] == 413
    assert transfer(proxy, "/api/v1/search", [b"a" * 20000]) == (200, b"20000")


def test_legacy_multipart_has_exact_additional_envelope_allowance(proxy):
    total = 32768 + 65536
    assert transfer(proxy, "/api/v1/documents", [b"a" * total]) == (200, str(total).encode())
    assert transfer(proxy, "/api/v1/documents", [b"a" * (total + 1)])[0] == 413


def test_proxy_image_copies_its_body_limit_dependency():
    root = Path(__file__).resolve().parents[3]
    dockerfile = (root / "apps/web/Dockerfile").read_text()
    assert "/app/apps/web/request_body_limits.mjs ./request_body_limits.mjs" in dockerfile
