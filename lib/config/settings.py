from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
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
    enable_model_placeholders: bool = False
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
    embedding_visual_enabled: bool = True
    embedding_visual_dimensions: int = 2048
    embedding_visual_batch_size: int = 8
    embedding_visual_max_image_bytes: int = 10 * 1024 * 1024
    embedding_visual_timeout_seconds: int = 60
    model_mode: Literal["fixture", "live", "required"] = "fixture"
    model_qwen_url: str = "http://127.0.0.1:8100"
    model_qwen_hq_url: str = "http://127.0.0.1:8100"
    model_qwen_semantic_url: str = "http://127.0.0.1:8104"
    model_granite_url: str = "http://127.0.0.1:8101"
    model_text_embed_url: str = "http://127.0.0.1:8102"
    model_visual_embed_url: str = "http://127.0.0.1:8103"
    qwen_profile: str = "qwen3-vl-8b-instruct-nvfp4-local:v1"
    qwen_hq_profile: str = "qwen3-vl-8b-semantic-hq:v1"
    qwen_semantic_profile: str = "qwen3-vl-4b-semantic:v1"
    model_qwen_semantic_timeout_seconds: int = 180
    model_qwen_hq_timeout_seconds: int = 180
    qwen8_enabled: bool = False
    granite_profile: str = "granite-4.0-3b-vision-bf16:v1"
    text_embed_profile: str = "qwen3-embedding-4b-1536:v1"
    visual_embed_profile: str = "qwen3-vl-embedding-2b-2048:v1"
    model_input_scratch_root: Path = Path("/srv/structura/tmp/model-inputs")
    model_http_timeout_seconds: int = 60
    model_max_image_bytes: int = 10 * 1024 * 1024

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
