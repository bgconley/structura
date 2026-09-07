import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.structura_api.error_handlers import install_error_handling
from lib.uploads.errors import UploadError


@pytest.mark.parametrize(
    ("code", "status", "public_code"),
    [
        ("private/path source-content token=secret", 503, "upload_service_unavailable"),
        ("upload_capacity", 429, "upload_capacity"),
        ("upload_conflict", 409, "upload_conflict"),
    ],
)
def test_upload_error_boundary_has_static_code_correlation_and_bounded_retry(
    code, status, public_code, caplog
):
    app = FastAPI()
    install_error_handling(app)

    @app.get("/upload-error")
    def error():
        raise UploadError(code)

    with TestClient(app) as client:
        result = client.get("/upload-error")
    assert result.status_code == status
    assert result.json()["code"] == public_code
    assert "X-Request-ID" in result.headers
    assert result.headers.get("Retry-After") == ("5" if status == 429 else None)
    assert "token=secret" not in result.text + caplog.text
