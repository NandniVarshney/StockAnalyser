"""Fallback daily OHLCV — yfinance. Rate-limit risky; use sparingly."""

from __future__ import annotations

import asyncio
from datetime import date

import pandas as pd

from stockanalyser.providers.base import MarketDataProvider
from stockanalyser.utils.logging import get_logger
from stockanalyser.utils.ticker_map import to_yfinance

log = get_logger(__name__)


class YFinanceProvider(MarketDataProvider):
    name = "yfinance"

    async def fetch_daily(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        ticker = to_yfinance(symbol)
        return await asyncio.to_thread(self._fetch_sync, ticker, start, end)

    @staticmethod
    def _fetch_sync(ticker: str, start: date, end: date) -> pd.DataFrame:
        import yfinance as yf  # type: ignore[import-untyped]

        df = yf.download(
            ticker,
            start=start.isoformat(),
            end=end.isoformat(),
            interval="1d",
            progress=False,
            auto_adjust=False,
            group_by="column",
        )
        if df is None or df.empty:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

        # yfinance returns a MultiIndex column header when given a single ticker
        # (e.g. ("Open", "RELIANCE.NS")). Flatten by keeping only level 0.
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index().rename(
            columns={
                "Date": "date",
                "Datetime": "date",
                "index": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
        if "date" not in df.columns:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df[["date", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
