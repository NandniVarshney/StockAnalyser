"""News facade — merges multi-source, dedupes by URL, persists, returns window."""

from __future__ import annotations

import asyncio
import hashlib

from stockanalyser.providers.base import NewsArticleDTO
from stockanalyser.providers.news.finnhub_provider import FinnhubNewsProvider
from stockanalyser.providers.news.newsdata_provider import NewsDataProvider
from stockanalyser.providers.news.rss_provider import RssNewsProvider
from stockanalyser.storage.models import NewsArticle
from stockanalyser.storage.repositories import recent_news, upsert_news
from stockanalyser.utils.logging import get_logger

log = get_logger(__name__)


class NewsFacade:
    def __init__(
        self,
        finnhub: FinnhubNewsProvider | None = None,
        rss: RssNewsProvider | None = None,
        newsdata: NewsDataProvider | None = None,
    ) -> None:
        self.finnhub = finnhub or FinnhubNewsProvider()
        self.rss = rss or RssNewsProvider()
        self.newsdata = newsdata or NewsDataProvider()

    async def refresh_and_get(self, symbol: str, days: int = 7) -> list[NewsArticleDTO]:
        # Fetch from primary sources in parallel
        results = await asyncio.gather(
            self.finnhub.fetch(symbol, days),
            self.rss.fetch(symbol, days),
            return_exceptions=True,
        )
        articles: list[NewsArticleDTO] = []
        for res in results:
            if isinstance(res, Exception):
                log.warning("news_source_failed", error=str(res))
                continue
            articles.extend(res)

        # Fallback if everything else is empty
        if not articles:
            try:
                articles = await self.newsdata.fetch(symbol, days)
            except Exception as e:  # noqa: BLE001
                log.warning("newsdata_fallback_failed", error=str(e))

        # Persist (dedupe by URL hash via PK)
        upsert_news([self._to_row(a) for a in articles if a.url])

        # Return what's in the DB (canonical 7-day window)
        rows = recent_news(symbol, days=days)
        return [
            NewsArticleDTO(
                symbol=r.symbol,
                source=r.source,
                title=r.title,
                url=r.url,
                summary=r.summary,
                published_at=r.published_at,
            )
            for r in rows
        ]

    @staticmethod
    def _to_row(a: NewsArticleDTO) -> NewsArticle:
        return NewsArticle(
            id=hashlib.sha256(a.url.encode("utf-8")).hexdigest(),
            symbol=a.symbol,
            source=a.source,
            title=a.title,
            url=a.url,
            summary=a.summary,
            published_at=a.published_at,
        )
