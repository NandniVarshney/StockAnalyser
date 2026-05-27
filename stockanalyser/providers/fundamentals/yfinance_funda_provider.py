"""Sanity-check fundamentals via yfinance.info — covers P/E + market cap only."""

from __future__ import annotations

import asyncio

from stockanalyser.providers.base import FundamentalsDTO, FundamentalsProvider
from stockanalyser.utils.logging import get_logger
from stockanalyser.utils.ticker_map import to_yfinance
from stockanalyser.utils.time import now_ist

log = get_logger(__name__)


class YFinanceFundamentalsProvider(FundamentalsProvider):
    name = "yfinance"

    async def fetch(self, symbol: str) -> FundamentalsDTO:
        return await asyncio.to_thread(self._fetch_sync, symbol)

    def _fetch_sync(self, symbol: str) -> FundamentalsDTO:
        import yfinance as yf  # type: ignore[import-untyped]

        info = yf.Ticker(to_yfinance(symbol)).info or {}
        return FundamentalsDTO(
            symbol=symbol,
            fetched_at=now_ist().replace(tzinfo=None),
            source=self.name,
            pe=info.get("trailingPE"),
            pb=info.get("priceToBook"),
            roe=info.get("returnOnEquity"),
            debt_equity=info.get("debtToEquity"),
            eps=info.get("trailingEps"),
            market_cap=info.get("marketCap"),
            raw=info,
        )
