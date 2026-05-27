"""Parquet store for daily OHLCV — one file per symbol.

Schema:
    date (date), open (float), high (float), low (float),
    close (float), volume (int)
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from stockanalyser.config import get_settings


class ParquetStore:
    """Read-first / append-delta store for daily OHLCV per symbol."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        d = Path(base_dir or get_settings().parquet_dir)
        d.mkdir(parents=True, exist_ok=True)
        self.base_dir = d

    # ─── Paths ────────────────────────────────────────────────────────────
    def path_for(self, symbol: str) -> Path:
        return self.base_dir / f"{symbol.upper()}.parquet"

    def exists(self, symbol: str) -> bool:
        return self.path_for(symbol).is_file()

    # ─── Read ─────────────────────────────────────────────────────────────
    def read(self, symbol: str) -> pd.DataFrame:
        """Return full history as a DataFrame sorted by date ascending."""
        p = self.path_for(symbol)
        if not p.is_file():
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        df = pd.read_parquet(p)
        return df.sort_values("date").reset_index(drop=True)

    def last_date(self, symbol: str) -> date | None:
        df = self.read(symbol)
        if df.empty:
            return None
        last = df["date"].iloc[-1]
        if isinstance(last, pd.Timestamp):
            return last.date()
        if isinstance(last, date):
            return last
        return pd.to_datetime(last).date()

    # ─── Write ────────────────────────────────────────────────────────────
    def write(self, symbol: str, df: pd.DataFrame) -> None:
        """Full overwrite. Used for cold-start backfill."""
        self._validate(df)
        df.sort_values("date").to_parquet(self.path_for(symbol), index=False)

    def append(self, symbol: str, new_rows: pd.DataFrame) -> None:
        """Append new candles; drop duplicates on `date`."""
        if new_rows.empty:
            return
        self._validate(new_rows)
        existing = self.read(symbol)
        combined = (
            pd.concat([existing, new_rows], ignore_index=True)
            .drop_duplicates(subset=["date"], keep="last")
            .sort_values("date")
            .reset_index(drop=True)
        )
        combined.to_parquet(self.path_for(symbol), index=False)

    # ─── Validation ───────────────────────────────────────────────────────
    @staticmethod
    def _validate(df: pd.DataFrame) -> None:
        required = {"date", "open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Parquet OHLCV DataFrame missing columns: {missing}")
