"""News facade — fetches via RSS, dedupes by URL hash, persists to SQLite.

Phase 1 uses RSS only. Finnhub/NewsData were removed because Finnhub's free
tier doesn't cover Indian stocks and NewsData added little incremental value.
Both can be re-added in Phase 2 when we have paid plans / wider coverage.
"""

from __future__ import annotations

from stockanalyser.providers.base import NewsArticleDTO
from stockanalyser.providers.news.rss_provider import RssNewsProvider
from stockanalyser.storage.models import NewsArticle
from stockanalyser.storage.repositories import recent_news, upsert_news
from stockanalyser.utils.hashing import stable_hash
from stockanalyser.utils.logging import get_logger

log = get_logger(__name__)


def _dto_to_orm(d: NewsArticleDTO) -> NewsArticle:
    return NewsArticle(
        id=stable_hash(d.url),
        symbol=d.symbol,
        source=d.source,
        title=d.title,
        url=d.url,
        summary=d.summary,
        published_at=d.published_at,
    )


def _orm_to_dto(r: NewsArticle) -> NewsArticleDTO:
    return NewsArticleDTO(
        symbol=r.symbol,
        source=r.source,
        title=r.title,
        url=r.url,
        summary=r.summary,
        published_at=r.published_at,
    )


class NewsFacade:
    def __init__(self, rss: RssNewsProvider | None = None) -> None:
        self.rss = rss or RssNewsProvider()

    async def get_recent_news(self, symbol: str, days: int = 7) -> list[NewsArticleDTO]:
        """Fetch fresh articles, persist (dedupe by URL hash), return last N days."""
        try:
            fetched = await self.rss.fetch(symbol, days)
        except Exception as e:  # noqa: BLE001
            log.warning("rss_fetch_failed", symbol=symbol, error=str(e))
            fetched = []

        if fetched:
            inserted = upsert_news([_dto_to_orm(a) for a in fetched])
            log.info("news_persisted", symbol=symbol, fetched=len(fetched), inserted=inserted)

        # Always read from SQLite so we benefit from prior runs' dedupe + retention.
        rows = recent_news(symbol, days=days)
        return [_orm_to_dto(r) for r in rows]
