"""Pytest fixtures — isolate tests from real DB / network."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _isolated_storage(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Each test gets a fresh temp dir for SQLite + Parquet."""
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("SQLITE_PATH", os.path.join(tmp, "test.db"))
        monkeypatch.setenv("PARQUET_DIR", os.path.join(tmp, "ohlcv"))
        # Disable real cron during tests
        monkeypatch.setenv("LOG_LEVEL", "WARNING")

        # Reset the cached Settings singleton
        from stockanalyser.config.settings import get_settings

        get_settings.cache_clear()
        yield
        get_settings.cache_clear()
