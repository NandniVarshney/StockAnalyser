"""Screener.in scraper — primary fundamentals source.

ToS note (see PLAN.md §2.2):
  - 1–2 req/sec with jitter
  - identifying User-Agent
  - internal/personal use only, no redistribution
  - cache 24h so we hit the site once a day at most

This is a SKELETON. The actual selector logic should be filled in carefully —
Screener occasionally renames CSS classes.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

from bs4 import BeautifulSoup

from stockanalyser.providers.base import FundamentalsDTO, FundamentalsProvider
from stockanalyser.utils.http import async_client, get_with_retries
from stockanalyser.utils.logging import get_logger
from stockanalyser.utils.ticker_map import to_screener_slug
from stockanalyser.utils.time import now_ist

log = get_logger(__name__)

BASE = "https://www.screener.in/company/{slug}/consolidated/"


class ScreenerProvider(FundamentalsProvider):
    name = "screener"

    async def fetch(self, symbol: str) -> FundamentalsDTO:
        slug = to_screener_slug(symbol).upper()
        url = BASE.format(slug=slug)

        # Polite jitter
        await asyncio.sleep(random.uniform(0.5, 1.5))

        async with async_client(timeout=20.0) as c:
            resp = await get_with_retries(c, url, retries=2)
            resp.raise_for_status()
            html = resp.text

        parsed = self._parse_html(html)
        return FundamentalsDTO(
            symbol=symbol,
            fetched_at=now_ist().replace(tzinfo=None),
            source=self.name,
            pe=parsed.get("pe"),
            pb=parsed.get("pb"),
            roe=parsed.get("roe"),
            roce=parsed.get("roce"),
            debt_equity=parsed.get("debt_equity"),
            eps=parsed.get("eps"),
            market_cap=parsed.get("market_cap"),
            revenue_yoy=parsed.get("revenue_yoy"),
            profit_yoy=parsed.get("profit_yoy"),
            raw=parsed,
        )

    # ─── HTML parsing (best-effort, defensive) ───────────────────────────
    @staticmethod
    def _parse_html(html: str) -> dict[str, Any]:
        """Extract the top-info ratio block from a Screener company page.

        TODO: finalise selectors once friend's fundamental strategy lands.
        Returns a dict that may contain any subset of:
          pe, pb, roe, roce, debt_equity, eps, market_cap, revenue_yoy, profit_yoy
        """
        soup = BeautifulSoup(html, "lxml")
        out: dict[str, Any] = {}

        labels = {
            "Stock P/E": "pe",
            "Price to book value": "pb",
            "ROE": "roe",
            "ROCE": "roce",
            "Debt to equity": "debt_equity",
            "EPS": "eps",
            "Market Cap": "market_cap",
        }
        for li in soup.select("ul#top-ratios li"):
            label_el = li.select_one(".name")
            value_el = li.select_one(".value .number")
            if not label_el or not value_el:
                continue
            label = label_el.get_text(strip=True)
            if label in labels:
                try:
                    out[labels[label]] = float(value_el.get_text(strip=True).replace(",", ""))
                except ValueError:
                    pass
        return out
