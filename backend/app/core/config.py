"""Application settings, read from environment variables (see .env.example)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AAHAR_", extra="ignore")

    env: str = "dev"
    # The API connects as the non-owner role `aahar_app`, so row-level security applies (ADR-0006).
    database_url: str = "postgresql+psycopg://aahar_app:change-me-demo@localhost:5442/aaharos"
    # Migrations run as the database owner.
    migration_database_url: str = "postgresql+psycopg://aahar:change-me-demo@localhost:5442/aaharos"
    # Password given to `aahar_app` when the first migration creates it (DEMO default; set your own in .env).
    app_db_password: str = "change-me-demo"  # noqa: S105 - DEMO default, overridden from .env
    oracle_path: Path = _REPO_ROOT / "benchmark" / "expected_results.yaml"
    benchmark_results_path: Path = _REPO_ROOT / "benchmark" / "results" / "latest.json"
    cors_origins: list[str] = ["http://localhost:5180"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
