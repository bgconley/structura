from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STRUCTURA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="development", alias="STRUCTURA_ENV")
    runtime_root: Path = Path("/srv/structura")
    database_url: str = "postgresql://structura:structura@localhost:5432/structura"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    web_origin: str = "http://localhost:3000"
    session_cookie_name: str = "structura_session"
    csrf_cookie_name: str = "structura_csrf"
    session_cookie_secure: bool = False
    session_ttl_minutes: int = 60 * 24
    magic_link_ttl_minutes: int = 15
    return_magic_link_tokens_for_tests: bool = False
    contracts_dir: Path = Path("contracts")
    database_dir: Path = Path("database")
    queue_transport: str = "pgmq"
    max_upload_bytes: int = 100 * 1024 * 1024
    watched_folder_root: Path = Path("/srv/structura/imports")
    docling_max_num_pages: int = 500
    docling_max_file_size: int = 100 * 1024 * 1024
    docling_store_markdown: bool = True
    docling_store_html: bool = True
    docling_do_ocr: bool = False
    docling_do_table_structure: bool = True
    docling_ocr_model_root: Path = Path("/srv/structura/cache/rapidocr")
    docling_ocr_backend: str = "torch"
    embedding_text_dimensions: int = 1536
    embedding_text_enabled: bool = True
    embedding_visual_enabled: bool = True
    embedding_visual_dimensions: int = 2048
    embedding_visual_batch_size: int = 8
    embedding_visual_max_image_bytes: int = 10 * 1024 * 1024
    embedding_visual_timeout_seconds: int = 60
    model_mode: Literal["fixture", "live", "required"] = "fixture"
    # Extractive-first text lanes (ADR 0006, E0-E2). Both lanes passed their
    # GPU A/B gates vs the pinned run-9 baseline on 2026-06-10 (tables: runs
    # 20260610T093120Z/095035Z; KVP: runs 20260610T111457Z/112154Z) and
    # default on. The vision path remains the fallback for difficult pages
    # and text-lane abstentions.
    text_lane_tables_enabled: bool = Field(default=True, alias="STRUCTURA_TEXT_LANE_TABLES")
    text_lane_kvp_enabled: bool = Field(default=True, alias="STRUCTURA_TEXT_LANE_KVP")
    qwen_vision_fallback_enabled: bool = Field(default=True, alias="STRUCTURA_QWEN_VISION_FALLBACK")
    # Deterministic-primary planning (ADR 0006 X4, E3). Passed its GPU gate
    # on 2026-06-10 (runs 20260610T205327Z/210049Z: identical baseline
    # fingerprints across ingests, zero dead letters, forced-Qwen-failure
    # canary degraded to full deterministic coverage) and defaults on.
    deterministic_planner_enabled: bool = Field(
        default=True, alias="STRUCTURA_DETERMINISTIC_PLANNER"
    )
    model_qwen_semantic_url: str = "http://127.0.0.1:8104"
    model_granite_url: str = "http://127.0.0.1:8101"
    model_text_embed_url: str = "http://127.0.0.1:8102"
    model_visual_embed_url: str = "http://127.0.0.1:8103"
    qwen_semantic_profile: str = "qwen3-vl-8b-fp8-semantic:v1"
    qwen_vision_profile: str = Field(
        default="qwen3-vl-8b-fp8-semantic:v1", alias="STRUCTURA_QWEN_VISION_PROFILE"
    )
    model_qwen_semantic_timeout_seconds: int = 300
    # Warn when the conservative pre-dispatch Qwen input estimate (prompt +
    # schema + visual tokens + requested output budget) exceeds this fraction
    # of the profile's max_model_len. Telemetry only; <= 0 disables.
    qwen_input_budget_warn_fraction: float = 0.9
    granite_profile: str = "granite-4.0-3b-vision-bf16:v1"
    text_embed_profile: str = "qwen3-embedding-4b-1536:v1"
    visual_embed_profile: str = "qwen3-vl-embedding-2b-2048:v1"
    model_input_scratch_root: Path = Path("/srv/structura/tmp/model-inputs")
    model_http_timeout_seconds: int = 60
    model_max_image_bytes: int = 10 * 1024 * 1024

    @model_validator(mode="after")
    def reject_historical_live_semantic_profiles(self) -> Settings:
        historical_profiles = {
            "qwen3-vl-2b-semantic:v1",
            "qwen3-vl-4b-semantic:v1",
        }
        if self.model_mode in {"live", "required"} and (
            self.qwen_semantic_profile in historical_profiles
        ):
            raise ValueError(
                "Live Phase 8.5 Smart Parse must use "
                "qwen3-vl-8b-fp8-semantic:v1; got "
                f"{self.qwen_semantic_profile}."
            )
        return self

    @property
    def canonical_objects_root(self) -> Path:
        return self.runtime_root / "objects" / "canonical"

    @property
    def derived_objects_root(self) -> Path:
        return self.runtime_root / "objects" / "derived"

    @property
    def export_objects_root(self) -> Path:
        return self.runtime_root / "objects" / "exports"


@lru_cache
def get_settings() -> Settings:
    return Settings()
