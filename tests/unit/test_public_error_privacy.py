from __future__ import annotations

import json
import logging
import traceback
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from apps.api.structura_api.error_handlers import ResponseTransmissionError, install_error_handling
from lib.auth.authorization_policy import AuthorizationError
from lib.evidence.errors import EvidenceUnavailable
from lib.jobs.public_errors import public_job_error, safe_job_failure
from lib.jobs.public_results import public_job_result

PRIVATE = "/srv/structura/private-patient.pdf token=private-token patient-private-excerpt"


def test_job_error_persistence_discards_arbitrary_values_and_keys() -> None:
    error = safe_job_failure(
        PRIVATE,
        PRIVATE,
        {
            PRIVATE: PRIVATE,
            "exception_message": PRIVATE,
            "traceback": PRIVATE,
            "status_code": PRIVATE,
            "response_bytes": 128,
            "model_failure_policy": PRIVATE,
            "model_runtime_details": {"message": PRIVATE},
        },
    )
    assert PRIVATE not in json.dumps(error)
    assert error["details"] == {"response_bytes": 128}
    assert error["error_class"] == "ProcessingError"
    assert UUID(error["error_id"])
    assert error["error_id"] in str(public_job_error(error))


@pytest.mark.parametrize(
    "error",
    [
        {"message": PRIVATE, "last_error": PRIVATE},
        {"public_code": PRIVATE, "error_id": PRIVATE},
        {"public_code": [PRIVATE], "details": {"message": PRIVATE}},
        {"taxonomy_code": PRIVATE, "exception_class": PRIVATE},
    ],
)
def test_historical_or_forged_job_errors_cannot_echo_source_content(error) -> None:
    assert "processing failed" in str(public_job_error(error)).lower()
    assert PRIVATE not in str(public_job_error(error))


def test_safe_timeout_retains_actionable_reason_without_exception_text() -> None:
    error = safe_job_failure("ModelTimeoutError", PRIVATE)
    assert "did not respond in time" in str(public_job_error(error))
    assert public_job_error({}) is None
    assert public_job_error(None) is None


def test_legacy_result_details_are_not_an_unfiltered_public_response() -> None:
    document_id = str(uuid4())
    result = public_job_result(
        {
            "document_id": document_id,
            "page_count": 2,
            "parse_status": "succeeded",
            "error_message": PRIVATE,
            "model_output": {"details": PRIVATE},
            "model_name": PRIVATE,
            "family": PRIVATE,
            "extraction_id": PRIVATE,
            "queued_granite_job_ids": [PRIVATE],
            "element_count": PRIVATE,
            "phase8_quality": {"review_required": True, "error": PRIVATE},
            "modality_counts": {"text": 2, "image": PRIVATE},
        }
    )
    assert PRIVATE not in json.dumps(result)
    assert result == {
        "document_id": document_id,
        "page_count": 2,
        "parse_status": "succeeded",
        "phase8_quality": {"review_required": True},
        "modality_counts": {"text": 2},
    }


class NumericInput(BaseModel):
    amount: int


def _app() -> FastAPI:
    app = FastAPI()
    install_error_handling(app)

    @app.get("/unexpected")
    def unexpected() -> None:
        raise RuntimeError(PRIVATE)

    @app.get("/known-error")
    def known_error() -> None:
        raise HTTPException(status_code=400, detail=PRIVATE)

    @app.get("/denied")
    def denied() -> None:
        raise AuthorizationError(PRIVATE)

    @app.get("/retained-evidence")
    def retained_evidence() -> None:
        raise EvidenceUnavailable(PRIVATE)

    @app.get("/broken-stream")
    async def broken_stream() -> StreamingResponse:
        async def body():
            yield b"partial document bytes"
            raise RuntimeError(PRIVATE)

        return StreamingResponse(body())

    @app.post("/validate")
    def validate(value: NumericInput) -> dict[str, int]:
        return {"amount": value.amount}

    @app.get("/documents/{document_id}")
    def read_document(document_id: str) -> dict[str, str]:
        return {"status": "ok"}

    return app


@pytest.mark.parametrize(
    ("path", "status"),
    [("/unexpected", 500), ("/known-error", 400), ("/denied", 403), ("/retained-evidence", 404)],
)
def test_api_failures_and_correlation_do_not_echo_private_strings(path, status, caplog) -> None:
    caplog.set_level(logging.INFO, logger="structura")
    with TestClient(_app()) as client:
        response = client.get(path, headers={"X-Request-ID": PRIVATE})
    assert response.status_code == status
    assert PRIVATE not in response.text
    if path == "/retained-evidence":
        assert response.json() == {"detail": "Retained generation is unavailable."}
    assert UUID(response.headers["X-Request-ID"])
    assert all(PRIVATE not in record.getMessage() for record in caplog.records)


def test_validation_errors_do_not_serialize_private_input_or_extra_keys() -> None:
    with TestClient(_app()) as client:
        response = client.post("/validate", json={"amount": PRIVATE, PRIVATE: PRIVATE})
    assert response.status_code == 422
    assert PRIVATE not in response.text


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (409, "This field changed since it was loaded. Reload it before saving your decision."),
        (400, "A confirmation must keep the existing field's value type."),
        (422, "A correction must keep the existing field's value type."),
    ],
)
def test_review_conflicts_keep_safe_instructions_without_echoing_extra_content(status, message):
    app = FastAPI()
    install_error_handling(app)

    @app.get("/review-decision")
    def decision(include_private: bool = False):
        raise HTTPException(
            status_code=status, detail=message + PRIVATE if include_private else message
        )

    with TestClient(app) as client:
        response = client.get("/review-decision")
        assert response.status_code == status
        assert response.json() == {"detail": message}
        redacted = client.get("/review-decision?include_private=true")
        assert redacted.status_code == status
        assert PRIVATE not in redacted.text
        assert redacted.json()["detail"] != message + PRIVATE


def test_request_logging_uses_route_template_and_validated_reference(caplog) -> None:
    caplog.set_level(logging.INFO, logger="structura")
    reference = str(uuid4())
    with TestClient(_app()) as client:
        response = client.get(
            "/documents/private-patient-identifier", headers={"X-Request-ID": reference}
        )
    assert response.headers["X-Request-ID"] == reference
    events = [
        json.loads(record.getMessage()) for record in caplog.records if record.name == "structura"
    ]
    assert events[-1]["route"] == "/documents/{document_id}"
    assert "private-patient-identifier" not in json.dumps(events)


def test_logging_sink_failure_does_not_fail_a_successful_request(monkeypatch) -> None:
    def broken_sink(*_args, **_kwargs) -> None:
        raise RuntimeError(PRIVATE)

    monkeypatch.setattr("apps.api.structura_api.error_handlers.log_event", broken_sink)
    with TestClient(_app()) as client:
        response = client.get("/documents/example")
    assert response.status_code == 200
    assert PRIVATE not in response.text


def test_interrupted_stream_aborts_with_safe_exception_and_honest_status(caplog) -> None:
    caplog.set_level(logging.INFO, logger="structura")
    with TestClient(_app()) as client:
        with pytest.raises(ResponseTransmissionError) as failure:
            client.get("/broken-stream")
    assert PRIVATE not in "".join(traceback.format_exception(failure.value))
    events = [
        json.loads(record.getMessage()) for record in caplog.records if record.name == "structura"
    ]
    assert events[-1]["status_code"] == 200  # Headers were already sent.
    assert events[-1]["response_complete"] is False
    assert events[-1]["processing_failed"] is True


def test_method_denial_preserves_safe_allow_header() -> None:
    with TestClient(_app()) as client:
        response = client.post("/unexpected")
    assert response.status_code == 405
    assert "GET" in response.headers["Allow"]
