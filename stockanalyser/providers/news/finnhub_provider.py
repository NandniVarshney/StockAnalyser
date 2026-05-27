"""Finnhub company news — supports `.NS` Indian tickers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from stockanalyser.config import get_settings
from stockanalyser.providers.base import NewsArticleDTO, NewsProvider
from stockanalyser.utils.http import async_client, get_with_retries
from stockanalyser.utils.logging import get_logger
from stockanalyser.utils.ticker_map import to_finnhub

log = get_logger(__name__)


class FinnhubNewsProvider(NewsProvider):
    name = "finnhub"
    BASE = "https://finnhub.io/api/v1/company-news"

    async def fetch(self, symbol: str, days: int = 7) -> list[NewsArticleDTO]:
        api_key = get_settings().finnhub_api_key
        if not api_key:
            log.warning("finnhub_api_key_missing")
            return []

        ticker = to_finnhub(symbol)
        today = datetime.now(timezone.utc).date()
        start = today - timedelta(days=days)
        params = {
            "symbol": ticker,
            "from": start.isoformat(),
            "to": today.isoformat(),
            "token": api_key,
        }
        async with async_client(timeout=15.0) as c:
            resp = await get_with_retries(c, self.BASE, params=params)
            resp.raise_for_status()
            items = resp.json() or []

        out: list[NewsArticleDTO] = []
        for it in items:
            published = datetime.fromtimestamp(it["datetime"], tz=timezone.utc)
            out.append(
                NewsArticleDTO(
                    symbol=symbol,
                    source=self.name,
                    title=it.get("headline") or "",
                    url=it.get("url") or "",
                    summary=it.get("summary"),
                    published_at=published.replace(tzinfo=None),
                )
            )
        return out
