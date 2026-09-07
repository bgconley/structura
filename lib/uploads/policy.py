"""Configurable validation bounds, not measured production capacity or SLOs."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from lib.uploads.models import UploadModel


class UploadPolicy(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STRUCTURA_UPLOAD_", extra="ignore", frozen=True)
    max_file_bytes: int = Field(default=100 * 1024 * 1024, gt=0, le=100 * 1024 * 1024)
    actor_active_limit: int = Field(default=2, gt=0, le=100)
    global_active_limit: int = Field(default=4, gt=0, le=1000)
    actor_reserved_bytes: int = Field(default=200 * 1024 * 1024, gt=0)
    global_reserved_bytes: int = Field(default=400 * 1024 * 1024, gt=0)
    queue_reference_limit: int = Field(default=100, gt=0, le=1000)
    absolute_seconds: int = Field(default=600, gt=0, le=3600)
    idle_seconds: int = Field(default=30, gt=0, le=300)
    lease_seconds: int = Field(default=60, gt=0, le=300)
    held_seconds: int = Field(default=1800, gt=0, le=86400)
    inactive_seconds: int = Field(default=1800, gt=0, le=86400)
    cleanup_lease_seconds: int = Field(default=60, gt=0, le=300)
    lock_wait_seconds: float = Field(default=1, ge=0, le=5)
    control_bytes: int = Field(default=16 * 1024, gt=0, le=16 * 1024)

    def public(self) -> UploadPolicyRead:
        return UploadPolicyRead(
            **self.model_dump(
                exclude={"lease_seconds", "cleanup_lease_seconds", "lock_wait_seconds"}
            ),
        )


class UploadPolicyRead(UploadModel):
    protocol: str = "structura.upload_attempt.v1"
    available: bool = True
    max_file_bytes: int
    actor_active_limit: int
    global_active_limit: int
    actor_reserved_bytes: int
    global_reserved_bytes: int
    queue_reference_limit: int
    absolute_seconds: int
    idle_seconds: int
    held_seconds: int
    inactive_seconds: int
    control_bytes: int
    mime_types: tuple[str, ...] = (
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/tiff",
        "image/webp",
    )
    validation: str = "recognized_signature_and_metadata_consistency"
