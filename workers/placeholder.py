from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from lib.jobs import record_service_health


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Structura worker placeholder")
    parser.add_argument("--worker", required=True)
    parser.add_argument("--heartbeat-seconds", type=int, default=30)
    parser.add_argument("--health-host", default="127.0.0.1")
    parser.add_argument("--health-port", type=int, default=0)
    return parser.parse_args()


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


def main() -> None:
    args = parse_args()
    running = True
    server = start_health_server(args.worker, args.health_host, args.health_port)

    def handle_stop(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    print(f"{args.worker}: placeholder started", flush=True)
    while running:
        print(f"{args.worker}: heartbeat", flush=True)
        try:
            record_service_health(
                service_name=args.worker,
                status="ok",
                metrics={"heartbeat_seconds": args.heartbeat_seconds},
            )
        except Exception as exc:
            print(f"{args.worker}: health snapshot skipped: {exc}", flush=True)
        time.sleep(args.heartbeat_seconds)
    if server:
        server.shutdown()
    print(f"{args.worker}: placeholder stopped", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
