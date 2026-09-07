"""Public error and request-log boundary; never serialize exception contents."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from lib.auth.authorization_policy import AuthorizationError
from lib.observability import log_event

_SAFE_DETAILS = frozenset(
    {
        "Not authenticated",
        "Authentication failed.",
        "Permission denied",
        "CSRF token required",
        "Household required",
        "Document not found",
        "Asset not found",
        "Job not found",
        "documentId mismatch",
        "Unsupported correction value type.",
        "Money requires an amount and currency only.",
        "Money currency must match the field currency.",
        "Money requires a three-letter uppercase currency code.",
        "Enter a whole integer within the supported range.",
        "A boolean correction must be true or false.",
        "A text correction must be a string.",
        "Enter a finite numeric amount without currency or separators.",
        "The amount exceeds the supported range.",
        "Use at most four decimal places; values are not rounded.",
        "Enter a valid calendar date in YYYY-MM-DD format.",
        "Enter a valid date and time with seconds and an explicit offset, "
        "such as 2026-09-07T14:30:00-04:00; use at most six fractional digits.",
        "JSON corrections support at most 64 nested levels.",
        "Enter valid JSON with finite numbers and string object keys.",
        "Selected candidate does not match this field.",
        "A field ordinal must be a positive integer.",
        "This field has a human decision. Reload it and include its current revision.",
        "This field changed since it was loaded. Reload it before saving your correction.",
    }
)
_STATUS_DETAILS = {
    400: "Invalid request.",
    401: "Not authenticated",
    403: "Permission denied",
    404: "Not found",
    405: "Method not allowed",
    409: "The request conflicts with the current state. Refresh and try again.",
    413: "The upload exceeds the supported size.",
    415: "This file type is not supported.",
    422: "Invalid request value.",
    429: "Too many requests. Please try again later.",
    500: "The request could not be completed. Contact an administrator with the request ID.",
    501: "This feature is not implemented yet.",
    503: "The service is temporarily unavailable. Please try again later.",
}


def _public_detail(status: int, detail: Any) -> str:
    if isinstance(detail, str):
        if detail in _SAFE_DETAILS:
            return detail
        # Retain useful instructions, never the interpolated path/key suffix.
        if "allowed intake roots" in detail:
            return "The watched folder must be within the allowed intake roots."
        if detail.startswith("Unsupported savedQuery key"):
            return "Unsupported savedQuery key. Use a supported search filter."
    return _STATUS_DETAILS.get(status, "The request could not be completed.")


def _request_id(value: str | None) -> str:
    try:
        return str(UUID(value)) if value else str(uuid4())
    except ValueError:
        return str(uuid4())


def _log_request(request: Request, status_code: int, *, completed: bool, failed: bool) -> None:
    route = request.scope.get("route")
    # Route templates contain declared names, while raw paths may contain PII.
    fields = {
        "correlation_id": request.state.correlation_id,
        "method": request.method
        if request.method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
        else "OTHER",
        "route": getattr(route, "path", None) or "unmatched",
        "status_code": status_code,
        "response_complete": completed,
        "processing_failed": failed,
    }
    try:
        log_event("api.request", **fields)
    except Exception:
        # A failing logging sink must not change an already handled request.
        # Do not log the logging exception: it may include the original payload.
        pass


class ResponseTransmissionError(RuntimeError):
    """Safe server-side failure after response headers have already been sent."""


class RequestBoundaryMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        reference = _request_id(Headers(scope=scope).get("X-Request-ID"))
        scope.setdefault("state", {})["correlation_id"] = reference
        started = completed = failed = False
        status_code = 500

        async def tracked_send(message: Message) -> None:
            nonlocal started, completed, status_code
            if message["type"] == "http.response.start":
                started = True
                status_code = message["status"]
                headers = MutableHeaders(raw=list(message.get("headers", [])))
                headers["X-Request-ID"] = reference
                message = {**message, "headers": headers.raw}
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                completed = True

        try:
            # Wrap the whole ASGI response, including body iteration/background
            # work; awaiting BaseHTTPMiddleware.call_next covers only headers.
            await self.app(scope, receive, tracked_send)
        except Exception:
            failed = True
            if started:
                # Abort an incomplete stream, never turn it into a successful
                # truncated download or attempt a second response. Suppress the
                # original exception chain in server traceback formatting.
                raise ResponseTransmissionError("Response processing was interrupted.") from None
            response = JSONResponse(status_code=500, content={"detail": _STATUS_DETAILS[500]})
            await response(scope, receive, tracked_send)
        finally:
            _log_request(Request(scope), status_code, completed=completed, failed=failed)


def install_error_handling(app: FastAPI) -> None:
    @app.exception_handler(AuthorizationError)
    async def authorization_error(_request: Request, _exc: AuthorizationError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": "Permission denied"})

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        headers: dict[str, str] = {}
        if exc.headers:
            retry_after = exc.headers.get("Retry-After", "")
            if retry_after.isascii() and retry_after.isdigit() and len(retry_after) <= 5:
                headers["Retry-After"] = retry_after
            auth = exc.headers.get("WWW-Authenticate")
            if auth in {"Bearer", "Basic"}:
                headers["WWW-Authenticate"] = auth
            allowed = [method.strip() for method in exc.headers.get("Allow", "").split(",")]
            if allowed and all(
                method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
                for method in allowed
            ):
                headers["Allow"] = ", ".join(allowed)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": _public_detail(exc.status_code, exc.detail)},
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        # Pydantic error input/context/location can include private document text.
        return JSONResponse(status_code=422, content={"detail": "Invalid request value."})

    app.add_middleware(RequestBoundaryMiddleware)
