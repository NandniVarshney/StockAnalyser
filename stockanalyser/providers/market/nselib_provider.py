"""Primary daily OHLCV provider — nselib.

`nselib` is sync, so we offload to a thread to keep our orchestrator async.
TODO: switch to chunked fetch + pagination when we exceed 365 days in one call.
"""

from __future__ import annotations

import asyncio
from datetime import date

import pandas as pd

from stockanalyser.providers.base import MarketDataProvider
from stockanalyser.utils.logging import get_logger
from stockanalyser.utils.ticker_map import to_nselib

log = get_logger(__name__)


class NselibProvider(MarketDataProvider):
    name = "nselib"

    async def fetch_daily(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        ticker = to_nselib(symbol)
        return await asyncio.to_thread(self._fetch_sync, ticker, start, end)

    # ─── Sync helper ──────────────────────────────────────────────────────
    @staticmethod
    def _fetch_sync(ticker: str, start: date, end: date) -> pd.DataFrame:
        from nselib import capital_market  # type: ignore[import-untyped]

        # nselib uses dd-mm-YYYY format
        df = capital_market.price_volume_and_deliverable_position_data(
            symbol=ticker,
            from_date=start.strftime("%d-%m-%Y"),
            to_date=end.strftime("%d-%m-%Y"),
        )
        return NselibProvider._normalize(df)

    @staticmethod
    def _normalize(df: pd.DataFrame) -> pd.DataFrame:
        """Normalize nselib columns to our schema."""
        col_map = {
            "Date": "date",
            "OpenPrice": "open",
            "HighPrice": "high",
            "LowPrice": "low",
            "ClosePrice": "close",
            "TotalTradedQuantity": "volume",
        }
        present = {k: v for k, v in col_map.items() if k in df.columns}
        out = df.rename(columns=present)[list(present.values())].copy()
        if "date" in out.columns:
            # nselib returns dates like "30-Apr-2025" (dd-MMM-YYYY).
            # `format="mixed"` lets pandas handle the occasional alternative
            # representation without crashing.
            out["date"] = pd.to_datetime(out["date"], format="mixed", dayfirst=True).dt.date
        for c in ("open", "high", "low", "close"):
            if c in out.columns:
                out[c] = pd.to_numeric(out[c].astype(str).str.replace(",", ""), errors="coerce")
        if "volume" in out.columns:
            out["volume"] = pd.to_numeric(
                out["volume"].astype(str).str.replace(",", ""), errors="coerce"
            ).fillna(0).astype("int64")
        return out.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
