"""NewsData.io — fallback for broader Indian publisher coverage."""

from __future__ import annotations

from datetime import datetime

from stockanalyser.config import get_settings, load_watchlist
from stockanalyser.providers.base import NewsArticleDTO, NewsProvider
from stockanalyser.utils.http import async_client, get_with_retries
from stockanalyser.utils.logging import get_logger

log = get_logger(__name__)


class NewsDataProvider(NewsProvider):
    name = "newsdata"
    BASE = "https://newsdata.io/api/1/news"

    async def fetch(self, symbol: str, days: int = 7) -> list[NewsArticleDTO]:
        api_key = get_settings().newsdata_api_key
        if not api_key:
            log.warning("newsdata_api_key_missing")
            return []

        query = self._company_name(symbol) or symbol
        params = {
            "apikey": api_key,
            "q": query,
            "country": "in",
            "language": "en",
            "category": "business",
        }
        async with async_client(timeout=15.0) as c:
            resp = await get_with_retries(c, self.BASE, params=params)
            resp.raise_for_status()
            body = resp.json() or {}

        out: list[NewsArticleDTO] = []
        for it in body.get("results", []):
            try:
                published = datetime.fromisoformat(
                    str(it.get("pubDate", "")).replace("Z", "+00:00")
                ).replace(tzinfo=None)
            except ValueError:
                continue
            out.append(
                NewsArticleDTO(
                    symbol=symbol,
                    source=self.name,
                    title=it.get("title") or "",
                    url=it.get("link") or "",
                    summary=it.get("description"),
                    published_at=published,
                )
            )
        return out

    @staticmethod
    def _company_name(symbol: str) -> str | None:
        for s in load_watchlist():
            if s.symbol == symbol:
                return s.name
        return None
