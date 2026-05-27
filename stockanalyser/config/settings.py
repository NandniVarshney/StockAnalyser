"""Pydantic settings — loaded from `.env` + environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single source of truth for runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── App ──────────────────────────────────────────────────────────────
    app_port: int = 8000
    log_level: str = "INFO"

    # ─── Storage ──────────────────────────────────────────────────────────
    sqlite_path: str = "db/stockanalyser.db"
    parquet_dir: str = "data/ohlcv"

    # ─── Behaviour (swing mode — daily only) ──────────────────────────────
    timezone: str = "Asia/Kolkata"
    fundamentals_ttl_hours: int = 24
    ohlcv_backfill_years: int = 2
    news_retention_days: int = 30

    # ─── Rovo Dev CLI ─────────────────────────────────────────────────────
    rovodev_serve_port: int = 8766
    rovodev_base_url: str = "http://localhost:8766"
    rovodev_binary_path: str | None = None
    rovodev_working_dir: str | None = None
    request_timeout_ms: int = 180_000
    per_agent_timeout_sec: int = 120
    aggregator_use_llm_reasoning: bool = False

    # ─── Atlassian context (consumed by `acli rovodev serve`) ─────────────
    atlassian_site: str | None = None
    atlassian_cloud_id: str | None = None
    atlassian_api_token: str | None = None
    atlassian_account_id: str | None = None

    # ─── External data API keys ───────────────────────────────────────────
    finnhub_api_key: str | None = None
    newsdata_api_key: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings singleton."""
    return Settings()
