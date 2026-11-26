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
    # MP03 authentication (ADR-0010). The secret signs access tokens; the default is DEMO-only and refused
    # outside dev/test. Access tokens are short-lived; refresh tokens rotate on every use.
    auth_secret: str = "dev-only-DEMO-secret-change-me-0123456789abcdef"  # noqa: S105 - refused outside dev/test
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cookie_secure: bool = False
    login_max_failures: int = 5
    login_max_failures_per_ip: int = 30
    login_window_minutes: int = 15
    oracle_path: Path = _REPO_ROOT / "benchmark" / "expected_results.yaml"
    benchmark_results_path: Path = _REPO_ROOT / "benchmark" / "results" / "latest.json"
    cors_origins: list[str] = ["http://localhost:5180"]
    # MP13 (T4): where the web app is served, for the batch-passport links printed in QR codes.
    public_base_url: str = "http://localhost:5180"
    # Deployment: the built web app (apps/web/dist) served by the API itself, so the demo is one address.
    web_dist: Path | None = None
    # Deployment: visitors may create their own sandbox factory (POST /api/signup).
    signups_open: bool = True
    # Sign-in: "local" (password checked here; development and tests) or "supabase" (Supabase Auth is the identity
    # server; the hosted demo). The URL and publishable key are public values the browser also uses.
    auth_mode: str = "local"
    supabase_url: str = ""
    supabase_key: str = ""
    # MP15: Judge Mode may replay the benchmark from the web (POST /api/judge/run, benchmark.run).
    judge_mode: bool = True


DEMO_AUTH_SECRET = Settings.model_fields["auth_secret"].default


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.env not in ("dev", "test") and settings.auth_secret == DEMO_AUTH_SECRET:
        raise RuntimeError("AAHAR_AUTH_SECRET must be set outside dev/test (the default is a DEMO value)")
    return settings
