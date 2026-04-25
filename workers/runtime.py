from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def start_health_server(worker_name: str, host: str, port: int) -> ThreadingHTTPServer | None:
    if port <= 0:
        return None

    class WorkerHealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path not in {"/", "/health", "/healthz"}:
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps({"status": "ok", "service": worker_name}).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer((host, port), WorkerHealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
