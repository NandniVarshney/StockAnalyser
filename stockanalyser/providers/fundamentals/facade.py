"""Cache-aware fundamentals facade — Screener.in only (Phase 1)."""

from __future__ import annotations

import json

from stockanalyser.providers.base import FundamentalsDTO
from stockanalyser.providers.fundamentals.screener_provider import ScreenerProvider
from stockanalyser.storage.models import FundamentalsCache
from stockanalyser.storage.repositories import get_fresh_fundamentals, upsert_fundamentals
from stockanalyser.utils.logging import get_logger

log = get_logger(__name__)


class FundamentalsFacade:
    def __init__(self, primary: ScreenerProvider | None = None) -> None:
        self.primary = primary or ScreenerProvider()

    async def get(self, symbol: str) -> FundamentalsDTO:
        """Return cached row if <24h old, else fetch + persist."""
        cached = get_fresh_fundamentals(symbol)
        if cached is not None:
            return self._row_to_dto(cached)

        dto = await self.primary.fetch(symbol)
        upsert_fundamentals(self._dto_to_row(dto))
        return dto

    # ─── Helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _dto_to_row(d: FundamentalsDTO) -> FundamentalsCache:
        return FundamentalsCache(
            symbol=d.symbol,
            fetched_at=d.fetched_at,
            source=d.source,
            pe=d.pe,
            pb=d.pb,
            roe=d.roe,
            roce=d.roce,
            debt_equity=d.debt_equity,
            eps=d.eps,
            market_cap=d.market_cap,
            revenue_yoy=d.revenue_yoy,
            profit_yoy=d.profit_yoy,
            raw_json=json.dumps(d.raw) if d.raw else None,
        )

    @staticmethod
    def _row_to_dto(r: FundamentalsCache) -> FundamentalsDTO:
        return FundamentalsDTO(
            symbol=r.symbol,
            fetched_at=r.fetched_at,
            source=r.source,
            pe=r.pe,
            pb=r.pb,
            roe=r.roe,
            roce=r.roce,
            debt_equity=r.debt_equity,
            eps=r.eps,
            market_cap=r.market_cap,
            revenue_yoy=r.revenue_yoy,
            profit_yoy=r.profit_yoy,
            raw=json.loads(r.raw_json) if r.raw_json else None,
        )
