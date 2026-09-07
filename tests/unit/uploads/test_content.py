from uuid import uuid4

import pytest
from pydantic import ValidationError

from lib.uploads.content import identify_content
from lib.uploads.errors import UploadError
from lib.uploads.models import UploadCreate, UploadDecision
from lib.uploads.policy import UploadPolicy


def command(filename="test.pdf", mime=None):
    return UploadCreate(
        operation_id=uuid4(),
        client_batch_id=uuid4(),
        filename=filename,
        declared_bytes=16,
        declared_mime_type=mime,
    )


@pytest.mark.parametrize(
    ("name", "header", "mime"),
    [
        ("test.pdf", b"%PDF-1.7\n", "application/pdf"),
        ("test.png", b"\x89PNG\r\n\x1a\n", "image/png"),
        ("test.jpg", b"\xff\xd8\xff\xe0", "image/jpeg"),
        ("test.tiff", b"II*\x00", "image/tiff"),
        ("test.tiff", b"MM\x00*", "image/tiff"),
        ("test.webp", b"RIFF\x00\x00\x00\x00WEBP", "image/webp"),
    ],
)
def test_actual_signature_identifies_format_without_claiming_decode(name, header, mime):
    assert identify_content(command(name, mime), header, "a" * 64, 16).mime_type == mime


@pytest.mark.parametrize(
    ("name", "mime", "header"),
    [
        ("test.pdf", "application/pdf", b"not a PDF"),
        ("test.pdf", None, b"\x89PNG\r\n\x1a\n"),
        ("test.pdf", "image/png", b"%PDF-1.7\n"),
        ("test.pdf", "text/plain", b"%PDF-1.7\n"),
    ],
)
def test_signature_and_declared_metadata_conflicts_rejected(name, mime, header):
    with pytest.raises(UploadError) as error:
        identify_content(command(name, mime), header, "a" * 64, 16)
    assert error.value.status_code == 415


def test_actual_count_must_equal_immutable_declared_size():
    with pytest.raises(UploadError) as error:
        identify_content(command(), b"%PDF-1.7\n", "a" * 64, 15)
    assert error.value.status_code == 422


def test_policy_explicitly_reports_reserved_capacity_and_signature_only_validation():
    result = UploadPolicy().public()
    assert result.global_reserved_bytes == 400 * 1024 * 1024
    assert result.actor_reserved_bytes == 200 * 1024 * 1024
    assert result.control_bytes == 16384
    assert result.validation == "recognized_signature_and_metadata_consistency"


def test_duplicate_command_requires_exact_reuse_identity():
    with pytest.raises(ValidationError):
        UploadDecision(revision=uuid4(), decision="use_existing")
    with pytest.raises(ValidationError):
        UploadDecision(revision=uuid4(), decision="keep_separate", document_id=uuid4())


def test_unknown_public_error_code_never_persists_private_content():
    error = UploadError("private original contents and path")
    assert error.code == "upload_service_unavailable"
    assert str(error) == "Upload service is unavailable."
