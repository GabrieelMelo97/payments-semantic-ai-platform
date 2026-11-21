"""Application configuration with strict Local-to-Cloud parity."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_project_root() -> Path:
    cwd = Path.cwd()
    if (cwd / "contracts" / "semantic_catalog.yaml").exists():
        return cwd
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "contracts" / "semantic_catalog.yaml").exists():
        return candidate
    return cwd


class Settings(BaseSettings):
    """Centralized settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["local", "gcp"] = Field(default="local")
    log_level: str = Field(default="INFO")

    # Local-First Storage
    project_root: Path = Field(default_factory=_default_project_root)
    local_data_dir: Path = Field(default=Path("data"))
    duckdb_path: Path = Field(default=Path("data/payments_warehouse.duckdb"))

    # GCP Configuration (only used when app_env == "gcp")
    gcp_project_id: str = Field(default="")
    gcp_region: str = Field(default="us-central1")
    gcs_raw_bucket: str = Field(default="")
    bq_dataset_raw: str = Field(default="payments_raw")
    bq_dataset_marts: str = Field(default="payments_marts")
    bq_max_bytes_billed: int = Field(default=104_857_600)  # 100 MB FinOps guardrail

    # AI Copilot Configuration
    ai_provider: Literal["deterministic", "vertex_ai", "gemini_api"] = Field(
        default="deterministic"
    )
    gemini_model: str = Field(default="gemini-2.5-flash")
    gemini_api_key: str = Field(default="")

    @property
    def resolved_data_dir(self) -> Path:
        if self.local_data_dir.is_absolute():
            return self.local_data_dir
        return self.project_root / self.local_data_dir

    @property
    def resolved_duckdb_path(self) -> Path:
        if self.duckdb_path.is_absolute():
            return self.duckdb_path
        return self.project_root / self.duckdb_path

    @property
    def semantic_catalog_path(self) -> Path:
        return self.project_root / "contracts" / "semantic_catalog.yaml"


def get_settings() -> Settings:
    """Return a fresh Settings instance."""
    return Settings()
