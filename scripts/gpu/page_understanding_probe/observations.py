"""Bounded actual transport evidence and adapter observations, private by construction."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from pathlib import Path

import httpx

from lib.document_parsing.qwen_page_parser import PageGenerationClient
from lib.document_processing.configuration_types import ParseRequestSettings
from lib.model_runtime.contracts import VisionGenerateRequest, VisionGenerateResponse
from scripts.gpu.probe_persisted_parse import write_private

MAX_ATTEMPTS = 3
MAX_RETAINED_BODY = 1024 * 1024


class ObservedTransport(httpx.BaseTransport):
    def __init__(self, directory: Path, transport: httpx.BaseTransport | None = None):
        self.directory = directory
        self.transport = transport or httpx.HTTPTransport(retries=0)
        self.started = self.responses = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if (
            self.started >= MAX_ATTEMPTS
            or request.method != "POST"
            or request.url.path != "/v1/chat/completions"
        ):
            raise RuntimeError("Probe actual HTTP attempt budget or route was exceeded.")
        self.started += 1
        number = self.started
        try:
            response = self.transport.handle_request(request)
        except Exception:
            write_private(
                self.directory / f"http-{number}.json",
                {"attempt": number, "response_received": False, "body_retained": False},
            )
            raise
        self.responses += 1
        if not isinstance(response.stream, httpx.SyncByteStream):
            raise RuntimeError("Probe requires a synchronous bounded response stream.")
        stream = RetainedBody(
            response.stream,
            self.directory,
            number,
            response.status_code,
            response.headers.get("content-encoding", "identity")[:200],
        )
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            stream=stream,
            extensions=response.extensions,
        )

    def close(self) -> None:
        self.transport.close()


class RetainedBody(httpx.SyncByteStream):
    def __init__(
        self,
        stream: httpx.SyncByteStream,
        directory: Path,
        number: int,
        status: int,
        content_encoding: str = "identity",
    ):
        self.stream, self.directory, self.number, self.status = stream, directory, number, status
        self.content_encoding = content_encoding
        self.retained = bytearray()
        self.complete = self.exceeded = self.closed = False
        self.iteration_started = self.diagnostic_drain_failed = False

    def __iter__(self) -> Iterator[bytes]:
        self.iteration_started = True
        for chunk in self.stream:
            space = MAX_RETAINED_BODY - len(self.retained)
            self.retained.extend(chunk[:space])
            self.exceeded = self.exceeded or len(chunk) > space
            yield chunk
        self.complete = True

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            if self.status >= 300 and not self.iteration_started:
                # The production HTTP adapter rejects error status before reading
                # its body. Retain a bounded wire prefix here, under that same
                # request's transport timeout, without another HTTP call or decode.
                try:
                    for _ in self:
                        if len(self.retained) >= MAX_RETAINED_BODY:
                            break
                except Exception:
                    self.diagnostic_drain_failed = True
            self.stream.close()
        finally:
            path = self.directory / f"http-{self.number}.body"
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as output:
                output.write(self.retained)
            write_private(
                self.directory / f"http-{self.number}.json",
                {
                    "attempt": self.number,
                    "http_status": self.status,
                    "response_received": True,
                    "encoding": "wire_bytes",
                    "content_encoding": self.content_encoding,
                    "diagnostic_drain_failed": self.diagnostic_drain_failed,
                    "retained_bytes": len(self.retained),
                    "retained_sha256": hashlib.sha256(self.retained).hexdigest(),
                    "entire_wire_body_retained": self.complete and not self.exceeded,
                    "body_limit_bytes": MAX_RETAINED_BODY,
                    "note": "Wire prefixes/compressed bodies do not certify decoded output.",
                },
            )


class ObservedClient:
    def __init__(
        self, client: PageGenerationClient, settings: ParseRequestSettings, directory: Path
    ):
        self.client, self.settings, self.directory = client, settings, directory
        self.started = self.completed = 0

    def generate(self, request: VisionGenerateRequest) -> VisionGenerateResponse:
        expected = self.settings
        if self.started >= MAX_ATTEMPTS or (
            request.max_output_tokens,
            request.temperature,
            request.seed,
            request.timeout_seconds,
        ) != (
            expected.max_output_tokens,
            expected.temperature,
            expected.seed,
            expected.timeout_seconds,
        ):
            raise RuntimeError("Probe adapter attempt budget or frozen settings differ.")
        self.started += 1
        write_private(
            self.directory / f"request-{self.started}.json",
            {
                "profile": request.profile_name,
                "prompt_version": request.prompt_version,
                "prompt": request.prompt,
                "response_schema_name": request.response_schema_name,
                "settings": expected.model_dump(mode="json"),
                "image_sha256": [image.sha256 for image in request.image_inputs],
            },
        )
        response = self.client.generate(request)
        self.completed += 1
        write_private(
            self.directory / f"response-{self.started}.json",
            {
                "raw_output": response.raw_text,
                "profile": response.profile_name,
                "served_model": response.model_name,
                "reported_model_version": response.model_version or None,
                "input_sha256": response.input_sha256,
                "finish_reason": response.finish_reason,
                "latency_ms": response.latency_ms,
                "usage": response.usage_json,
            },
        )
        return response
