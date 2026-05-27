"""News providers + cache-aware facade. Phase 1 = RSS only (Indian-stock friendly, free)."""

from stockanalyser.providers.news.facade import NewsFacade
from stockanalyser.providers.news.rss_provider import RssNewsProvider

__all__ = ["NewsFacade", "RssNewsProvider"]
