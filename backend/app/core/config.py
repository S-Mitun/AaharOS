"""Application settings, read from environment variables (see .env.example)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AAHAR_", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+psycopg://aahar:change-me-demo@localhost:5442/aaharos"
    oracle_path: Path = _REPO_ROOT / "benchmark" / "expected_results.yaml"
    benchmark_results_path: Path = _REPO_ROOT / "benchmark" / "results" / "latest.json"
    cors_origins: list[str] = ["http://localhost:5180"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
