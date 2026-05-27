"""Indian market RSS (Moneycontrol / ET / Livemint / Business Standard).

Strategy: pull the full feed (broad), then keyword-filter by company name
or symbol. Cheap, free, no API key.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser  # type: ignore[import-untyped]

from stockanalyser.config import load_sources, load_watchlist
from stockanalyser.providers.base import NewsArticleDTO, NewsProvider
from stockanalyser.utils.logging import get_logger

log = get_logger(__name__)


class RssNewsProvider(NewsProvider):
    name = "rss"

    async def fetch(self, symbol: str, days: int = 7) -> list[NewsArticleDTO]:
        feeds = load_sources().get("rss_feeds", [])
        keywords = self._keywords_for(symbol)
        if not keywords:
            log.warning("rss_no_keywords_for_symbol", symbol=symbol)
            return []

        tasks = [asyncio.to_thread(self._parse_feed, f) for f in feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        out: list[NewsArticleDTO] = []
        for res in results:
            if isinstance(res, Exception):
                continue
            for entry in res:
                title = (entry.get("title") or "").lower()
                summary = (entry.get("summary") or "").lower()
                if any(kw in title or kw in summary for kw in keywords):
                    out.append(self._to_dto(symbol, entry))
        return out

    # ─── Internals ────────────────────────────────────────────────────────
    @staticmethod
    def _parse_feed(feed_cfg: dict[str, str]) -> list[dict[str, object]]:
        parsed = feedparser.parse(feed_cfg["url"])
        return [{**e, "_source": feed_cfg["source"]} for e in parsed.entries]

    @staticmethod
    def _to_dto(symbol: str, entry: dict[str, object]) -> NewsArticleDTO:
        published_str = entry.get("published") or entry.get("updated")
        try:
            published = parsedate_to_datetime(str(published_str)).replace(tzinfo=None)
        except (TypeError, ValueError):
            published = datetime.utcnow()
        return NewsArticleDTO(
            symbol=symbol,
            source=str(entry.get("_source", "rss")),
            title=str(entry.get("title", "")),
            url=str(entry.get("link", "")),
            summary=str(entry.get("summary", ""))[:1000] or None,
            published_at=published,
        )

    @staticmethod
    def _keywords_for(symbol: str) -> list[str]:
        for s in load_watchlist():
            if s.symbol == symbol:
                # Drop common suffixes for broader matching
                name = s.name.lower()
                for suf in (" industries", " ltd", " limited", " corporation", " inc"):
                    name = name.removesuffix(suf)
                return [symbol.lower(), name]
        return [symbol.lower()]
