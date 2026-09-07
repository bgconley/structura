"""Validated maintenance schedule, separate from immutable upload policy."""

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CleanupRuntimeConfiguration(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STRUCTURA_UPLOAD_CLEANUP_", frozen=True)
    expected_database: str = Field(min_length=1, max_length=63)
    interval_seconds: float = Field(default=15, ge=1, le=300)
    limit: int = Field(default=100, ge=1, le=100)
    sweep_budget_seconds: float = Field(default=20, gt=0, le=60)
    stale_seconds: float = Field(default=90, ge=5, le=600)
    health_port: int = Field(default=8211, ge=0, le=65535)

    @model_validator(mode="after")
    def progress_budget(self) -> "CleanupRuntimeConfiguration":
        if self.stale_seconds <= max(self.interval_seconds, self.sweep_budget_seconds):
            raise ValueError("Cleanup health staleness must exceed schedule budgets.")
        return self


def retry_delay(interval_seconds: float, consecutive_failures: int) -> float:
    return float(min(120, interval_seconds * 2 ** min(max(0, consecutive_failures - 1), 8)))
