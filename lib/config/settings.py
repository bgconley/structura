from __future__ import annotations

from functools import lru_cache
from pathlib import Path

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
    contracts_dir: Path = Path("contracts")
    database_dir: Path = Path("database")
    queue_transport: str = "pgmq"
    enable_model_placeholders: bool = False
    max_upload_bytes: int = 100 * 1024 * 1024
    docling_max_num_pages: int = 500
    docling_max_file_size: int = 100 * 1024 * 1024
    docling_store_markdown: bool = True
    docling_store_html: bool = True
    docling_do_ocr: bool = False
    docling_do_table_structure: bool = True
    docling_ocr_model_root: Path = Path("/srv/structura/cache/rapidocr")
    docling_ocr_backend: str = "torch"

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
