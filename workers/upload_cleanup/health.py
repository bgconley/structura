"""Private process liveness and actual sweep progress, without request-time IO."""

import json
import threading
import time
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class CleanupHealth:
    def __init__(self, stale_seconds: float) -> None:
        self._lock = threading.Lock()
        self._stale_seconds = stale_seconds
        self._progress_at = time.monotonic()
        self._success_at: float | None = None
        self._state = "starting"
        self._failures = 0

    def progress(self) -> None:
        with self._lock:
            self._progress_at = time.monotonic()

    def finish(self, *, succeeded: bool) -> int:
        with self._lock:
            self._progress_at = time.monotonic()
            if self._state != "stopping":
                self._state = "ok" if succeeded else "degraded"
            self._failures = 0 if succeeded else self._failures + 1
            if succeeded:
                self._success_at = self._progress_at
            return self._failures

    def stop(self) -> None:
        with self._lock:
            self._state = "stopping"

    def snapshot(self) -> tuple[int, dict[str, object]]:
        with self._lock:
            now = time.monotonic()
            age = max(0, now - self._progress_at)
            status = "stalled" if age > self._stale_seconds else self._state
            return 200 if status == "ok" else 503, {
                "service": "worker-upload-cleanup",
                "status": status,
                "progressAgeSeconds": round(age, 3),
                "lastSuccessAgeSeconds": None
                if self._success_at is None
                else round(max(0, now - self._success_at), 3),
                "consecutiveFailures": self._failures,
            }


def start_cleanup_health(health: CleanupHealth, port: int) -> ThreadingHTTPServer | None:
    if not port:
        return None

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            payload: Mapping[str, object]
            if self.path == "/livez":
                status, payload = 200, {"service": "worker-upload-cleanup", "status": "alive"}
            elif self.path == "/healthz":
                status, payload = health.snapshot()
            else:
                status, payload = 404, {"status": "unavailable"}
            body = json.dumps(payload).encode()
            try:
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                return  # Disconnected local probes do not emit raw server tracebacks.

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
