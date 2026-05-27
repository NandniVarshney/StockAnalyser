"""Tiny CLI: `python -m stockanalyser <command>`.

Commands:
    ping                  - check Rovo CLI reachability
    fetch SYMBOL          - fetch OHLCV + fundamentals + news for one symbol
    analyze SYMBOL        - run the full analysis pipeline for one symbol
    analyze-all           - run the full watchlist
"""

from __future__ import annotations

import asyncio
import json
import sys

from stockanalyser.config import load_watchlist
from stockanalyser.orchestrator import analyze_stock, analyze_watchlist
from stockanalyser.providers.fundamentals import FundamentalsFacade
from stockanalyser.providers.market import MarketDataFacade
from stockanalyser.providers.news import NewsFacade
from stockanalyser.rovo_client import RovoClient
from stockanalyser.storage import init_db
from stockanalyser.storage.repositories import seed_watchlist
from stockanalyser.utils.logging import configure_logging


def _bootstrap() -> None:
    configure_logging()
    init_db()
    seed_watchlist([s.model_dump() for s in load_watchlist()])


async def _ping() -> None:
    ok = await RovoClient().health()
    print(json.dumps({"ok": ok}))


async def _fetch(symbol: str) -> None:
    symbol = symbol.upper()
    market, funda, news = MarketDataFacade(), FundamentalsFacade(), NewsFacade()
    ohlcv = await market.get_daily(symbol)
    f = await funda.get(symbol)
    n = await news.refresh_and_get(symbol, days=7)
    print(json.dumps({
        "symbol": symbol,
        "ohlcv_rows": len(ohlcv),
        "fundamentals_source": f.source,
        "news_count": len(n),
    }, default=str, indent=2))


async def _analyze(symbol: str) -> None:
    s = await analyze_stock(symbol.upper())
    print(s.model_dump_json(indent=2))


async def _analyze_all() -> None:
    results = await analyze_watchlist()
    print(json.dumps([r.model_dump() for r in results], default=str, indent=2))


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    _bootstrap()
    cmd, *args = sys.argv[1:]

    match cmd:
        case "ping":
            asyncio.run(_ping())
        case "fetch":
            if not args:
                sys.exit("usage: fetch SYMBOL")
            asyncio.run(_fetch(args[0]))
        case "analyze":
            if not args:
                sys.exit("usage: analyze SYMBOL")
            asyncio.run(_analyze(args[0]))
        case "analyze-all":
            asyncio.run(_analyze_all())
        case _:
            print(f"unknown command: {cmd}")
            print(__doc__)
            sys.exit(1)


if __name__ == "__main__":
    main()
