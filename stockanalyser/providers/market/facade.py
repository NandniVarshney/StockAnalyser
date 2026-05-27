"""Cache-aware facade — reads Parquet first, fetches only the delta.

This is the ONLY thing the orchestrator imports for market data. It hides:
  - cold-start backfill vs incremental append
  - primary (nselib) vs fallback (yfinance) provider selection
"""

from __future__ import annotations

from datetime import date, time, timedelta

import pandas as pd

from stockanalyser.config import get_settings
from stockanalyser.providers.market.nselib_provider import NselibProvider
from stockanalyser.providers.market.yfinance_provider import YFinanceProvider
from stockanalyser.storage.parquet_store import ParquetStore
from stockanalyser.utils.logging import get_logger
from stockanalyser.utils.time import now_ist, today_ist

log = get_logger(__name__)

# NSE closes at 15:30 IST. Before that, today's candle isn't available.
_MARKET_CLOSE = time(15, 30)


class MarketDataFacade:
    def __init__(
        self,
        store: ParquetStore | None = None,
        primary: NselibProvider | None = None,
        fallback: YFinanceProvider | None = None,
    ) -> None:
        self.store = store or ParquetStore()
        self.primary = primary or NselibProvider()
        self.fallback = fallback or YFinanceProvider()

    # ─── Public ───────────────────────────────────────────────────────────
    async def get_daily(self, symbol: str) -> pd.DataFrame:
        """Return full daily history (Parquet) for `symbol`, refreshed as needed."""
        last = self.store.last_date(symbol)
        latest_available = _latest_available_close_date()

        if last is None:
            await self._cold_start(symbol, latest_available)
        elif last < latest_available:
            await self._append_delta(symbol, last + timedelta(days=1), latest_available)
        else:
            log.debug("ohlcv_cache_fresh", symbol=symbol, last=str(last))

        return self.store.read(symbol)

    # ─── Internals ────────────────────────────────────────────────────────
    async def _cold_start(self, symbol: str, end: date) -> None:
        years = get_settings().ohlcv_backfill_years
        start = end - timedelta(days=365 * years + 10)
        log.info("ohlcv_cold_start", symbol=symbol, years=years, start=str(start), end=str(end))
        df = await self._fetch_with_fallback(symbol, start, end)
        if not df.empty:
            self.store.write(symbol, df)

    async def _append_delta(self, symbol: str, start: date, end: date) -> None:
        # Both endpoints in nselib are inclusive; if start>=end there's no gap
        # to fill (we already have everything up to end).
        if start > end:
            log.debug("ohlcv_no_gap", symbol=symbol)
            return
        log.info("ohlcv_append_delta", symbol=symbol, start=str(start), end=str(end))
        df = await self._fetch_with_fallback(symbol, start, end)
        if not df.empty:
            self.store.append(symbol, df)

    async def _fetch_with_fallback(
        self, symbol: str, start: date, end: date
    ) -> pd.DataFrame:
        if start > end:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
        try:
            df = await self.primary.fetch_daily(symbol, start, end)
            if df is not None and not df.empty:
                return df
            log.warning("primary_returned_empty", provider=self.primary.name, symbol=symbol)
        except Exception as e:  # noqa: BLE001
            log.warning("primary_failed", provider=self.primary.name, symbol=symbol, error=str(e))

        # Fallback
        try:
            return await self.fallback.fetch_daily(symbol, start, end)
        except Exception as e:  # noqa: BLE001
            log.error("fallback_failed", provider=self.fallback.name, symbol=symbol, error=str(e))
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])


# ─── Helpers ──────────────────────────────────────────────────────────────
def _latest_available_close_date() -> date:
    """Return the most recent date for which an EOD candle exists on NSE.

    Rules (IST):
      - Saturday / Sunday → previous Friday
      - Weekday before 15:30 → previous trading day
      - Weekday >= 15:30   → today
    """
    now = now_ist()
    today = now.date()
    weekday = today.weekday()  # 0 = Monday … 6 = Sunday

    if weekday == 5:                       # Saturday
        return today - timedelta(days=1)   # Friday
    if weekday == 6:                       # Sunday
        return today - timedelta(days=2)   # Friday

    # Weekday
    if now.time() < _MARKET_CLOSE:
        # Before today's close → use yesterday's candle (skip back over weekends)
        d = today - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d
    return today
