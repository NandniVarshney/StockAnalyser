"""Per-stock analysis pipeline + watchlist runner.

Flow (PUSH pattern — skills never read storage):
    1. Providers fetch raw data (cached, delta-only).
    2. Compute indicators + sector medians.
    3. Build a self-contained payload per agent.
    4. asyncio.gather over (TA, FA, NS) via RovoClient. return_exceptions=True
       so a single failure doesn't kill the run.
    5. Deterministic Python aggregator combines TA+FA → Suggestion.
    6. Persist agent_runs[3] + suggestions[1].
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict
from typing import Any

import pandas as pd

from stockanalyser.agents import AgentOutput, SkillKey, Suggestion
from stockanalyser.aggregator import aggregate
from stockanalyser.config import load_sources, load_watchlist, load_weights
from stockanalyser.config.yaml_loader import Stock
from stockanalyser.orchestrator.indicators import compute_indicators
from stockanalyser.orchestrator.sector_stats import compute_sector_medians
from stockanalyser.providers.fundamentals import FundamentalsFacade
from stockanalyser.providers.market import MarketDataFacade
from stockanalyser.providers.news import NewsFacade
from stockanalyser.rovo_client import RovoCLIError, RovoClient
from stockanalyser.storage.repositories import persist_agent_run, persist_suggestion
from stockanalyser.utils.logging import get_logger
from stockanalyser.utils.time import isoformat

log = get_logger(__name__)


# ─── Public ──────────────────────────────────────────────────────────────
async def analyze_stock(
    symbol: str,
    *,
    market: MarketDataFacade | None = None,
    funda: FundamentalsFacade | None = None,
    news: NewsFacade | None = None,
    rovo: RovoClient | None = None,
    sector_medians: dict[str, dict[str, float]] | None = None,
    parent_run_id: str | None = None,
) -> Suggestion:
    """Run the per-stock pipeline for one symbol."""
    market = market or MarketDataFacade()
    funda = funda or FundamentalsFacade()
    news = news or NewsFacade()
    rovo = rovo or RovoClient()
    parent_run_id = parent_run_id or str(uuid.uuid4())

    stock = _stock_meta(symbol)

    # 1. Fetch
    ohlcv = await market.get_daily(symbol)
    funda_dto = await funda.get(symbol)
    news_articles = await news.refresh_and_get(symbol, days=7)

    # 2. Compute
    indicators = compute_indicators(ohlcv)

    # 3. Build payloads
    payloads = {
        SkillKey.TECHNICAL: _ta_payload(symbol, ohlcv, indicators),
        SkillKey.FUNDAMENTAL: _fa_payload(symbol, funda_dto, stock, sector_medians),
        SkillKey.NEWS: _news_payload(symbol, news_articles),
    }

    # 4. Invoke — SERIAL across the 3 agents.
    #
    # The Rovo Dev CLI is single-session: concurrent POSTs to /v2/chat return
    # 409 Conflict. We still get watchlist-level concurrency via the semaphore
    # in analyze_watchlist (only 1 agent call in flight per Rovo instance at
    # any given time would be safer, but a single ag-call inside one analyze
    # is bounded by per_agent_timeout_sec).
    results: list[AgentOutput | BaseException] = []
    for key, payload in payloads.items():
        try:
            results.append(await rovo.run_skill(key, payload, run_id=parent_run_id))
        except Exception as e:  # noqa: BLE001
            results.append(e)

    ta_out = _safe_unpack(results[0], "technical", symbol, parent_run_id, payloads[SkillKey.TECHNICAL])
    fa_out = _safe_unpack(results[1], "fundamental", symbol, parent_run_id, payloads[SkillKey.FUNDAMENTAL])
    ns_out = _safe_unpack(results[2], "news", symbol, parent_run_id, payloads[SkillKey.NEWS])

    # 5. Aggregate (pure Python)
    weights_cfg = load_weights()
    suggestion = aggregate(
        symbol=symbol,
        technical=ta_out,
        fundamental=fa_out,
        news=ns_out,
        weights=weights_cfg.weights,
        thresholds=weights_cfg.thresholds,
        news_thresholds=weights_cfg.news_thresholds,
    )

    # 6. Persist final suggestion
    persist_suggestion(parent_run_id, suggestion)
    return suggestion


async def analyze_watchlist() -> list[Suggestion]:
    """Run analyze_stock for every active watchlist symbol (concurrency-limited)."""
    stocks = load_watchlist()
    funda_facade = FundamentalsFacade()

    # Pre-fetch fundamentals for sector medians (cheap due to 24h cache)
    sector_pairs: list[tuple[str, Any]] = []
    for s in stocks:
        try:
            dto = await funda_facade.get(s.symbol)
            sector_pairs.append((s.sector, dto))
        except Exception as e:  # noqa: BLE001
            log.warning("funda_prefetch_failed", symbol=s.symbol, error=str(e))
    sector_medians = compute_sector_medians(sector_pairs)

    parent_run_id = str(uuid.uuid4())

    # Rovo CLI is single-session — only ONE stock can be in the LLM phase
    # at a time. Data-fetch phase is fast and cached, so semaphore=1 is fine.
    sem = asyncio.Semaphore(1)

    async def _one(sym: str) -> Suggestion:
        async with sem:
            return await analyze_stock(
                sym, sector_medians=sector_medians, parent_run_id=parent_run_id
            )

    return await asyncio.gather(*[_one(s.symbol) for s in stocks])


# ─── Internals ───────────────────────────────────────────────────────────
def _stock_meta(symbol: str) -> Stock:
    for s in load_watchlist():
        if s.symbol == symbol:
            return s
    return Stock(symbol=symbol, name=symbol, sector="Unknown")


def _ta_payload(symbol: str, ohlcv: pd.DataFrame, indicators: dict[str, Any]) -> dict[str, Any]:
    """Push last 60 daily candles + indicator snapshot to the TA skill."""
    recent = ohlcv.tail(60).copy()
    recent["date"] = recent["date"].astype(str)
    return {
        "symbol": symbol,
        "as_of": isoformat(),
        "ohlcv_daily": recent.to_dict(orient="records"),
        "indicators": indicators,
    }


def _fa_payload(
    symbol: str,
    funda: Any,
    stock: Stock,
    sector_medians: dict[str, dict[str, float]] | None,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "as_of": isoformat(),
        "sector": stock.sector,
        "fundamentals": {
            k: v
            for k, v in asdict(funda).items()
            if k not in ("raw", "fetched_at", "source", "symbol") and v is not None
        },
        "sector_medians": (sector_medians or {}).get(stock.sector, {}),
        "data_freshness": funda.fetched_at.isoformat(),
    }


def _news_payload(symbol: str, articles: list[Any]) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "as_of": isoformat(),
        "news_articles": [
            {
                "title": a.title,
                "url": a.url,
                "summary": a.summary,
                "source": a.source,
                "published_at": a.published_at.isoformat(),
            }
            for a in articles
        ],
    }


def _safe_unpack(
    result: AgentOutput | BaseException,
    agent: str,
    symbol: str,
    parent_run_id: str,
    inputs: dict[str, Any],
) -> AgentOutput | None:
    """Persist the agent run (success or failure) and return the output (or None)."""
    run_id = str(uuid.uuid4())
    if isinstance(result, AgentOutput):
        persist_agent_run(
            run_id=run_id,
            parent_run_id=parent_run_id,
            symbol=symbol,
            agent=agent,
            output=result,
            inputs=inputs,
        )
        return result

    log.warning(
        "agent_failed",
        agent=agent,
        symbol=symbol,
        error=str(result),
        kind="rovo" if isinstance(result, RovoCLIError) else "other",
    )
    persist_agent_run(
        run_id=run_id,
        parent_run_id=parent_run_id,
        symbol=symbol,
        agent=agent,
        output=None,
        inputs=inputs,
    )
    return None
