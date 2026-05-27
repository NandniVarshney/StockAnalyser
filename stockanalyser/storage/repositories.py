"""Thin repository helpers — no business logic.

Keeps SQL out of orchestrator / agents / API handlers.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from stockanalyser.agents import AgentOutput, Suggestion
from stockanalyser.config import get_settings
from stockanalyser.storage.db import get_session
from stockanalyser.storage.models import (
    AgentRun,
    FundamentalsCache,
    NewsArticle,
    SuggestionRow,
    WatchlistRow,
)
from stockanalyser.utils.hashing import stable_hash
from stockanalyser.utils.time import now_ist


# ─── Watchlist ───────────────────────────────────────────────────────────
def seed_watchlist(stocks: list[dict[str, str]]) -> None:
    """Idempotent insert/update of watchlist rows."""
    with get_session() as s:
        for st in stocks:
            row = s.get(WatchlistRow, st["symbol"])
            if row is None:
                s.add(
                    WatchlistRow(
                        symbol=st["symbol"],
                        company_name=st["name"],
                        sector=st.get("sector"),
                    )
                )
            else:
                row.company_name = st["name"]
                row.sector = st.get("sector")
                row.active = True


def list_watchlist(active_only: bool = True) -> list[WatchlistRow]:
    with get_session() as s:
        q = select(WatchlistRow)
        if active_only:
            q = q.where(WatchlistRow.active.is_(True))
        return list(s.scalars(q.order_by(WatchlistRow.symbol)))


# ─── Fundamentals cache ──────────────────────────────────────────────────
def get_fresh_fundamentals(symbol: str) -> FundamentalsCache | None:
    ttl = timedelta(hours=get_settings().fundamentals_ttl_hours)
    cutoff = now_ist().replace(tzinfo=None) - ttl
    with get_session() as s:
        q = (
            select(FundamentalsCache)
            .where(FundamentalsCache.symbol == symbol)
            .where(FundamentalsCache.fetched_at >= cutoff)
            .order_by(FundamentalsCache.fetched_at.desc())
        )
        return s.scalars(q).first()


def upsert_fundamentals(row: FundamentalsCache) -> None:
    with get_session() as s:
        s.merge(row)


# ─── News (dedupe-by-URL via primary key) ────────────────────────────────
def upsert_news(articles: list[NewsArticle]) -> int:
    """INSERT OR IGNORE on URL hash. Returns count actually inserted."""
    if not articles:
        return 0
    with get_session() as s:
        stmt = sqlite_insert(NewsArticle).values(
            [
                {
                    "id": a.id,
                    "symbol": a.symbol,
                    "source": a.source,
                    "title": a.title,
                    "url": a.url,
                    "summary": a.summary,
                    "published_at": a.published_at,
                }
                for a in articles
            ]
        ).on_conflict_do_nothing(index_elements=["id"])
        result = s.execute(stmt)
        return result.rowcount or 0


def recent_news(symbol: str, days: int = 7) -> list[NewsArticle]:
    cutoff = now_ist().replace(tzinfo=None) - timedelta(days=days)
    with get_session() as s:
        q = (
            select(NewsArticle)
            .where(NewsArticle.symbol == symbol)
            .where(NewsArticle.published_at >= cutoff)
            .order_by(NewsArticle.published_at.desc())
        )
        return list(s.scalars(q))


def purge_old_news() -> int:
    retention_days = get_settings().news_retention_days
    cutoff = now_ist().replace(tzinfo=None) - timedelta(days=retention_days)
    with get_session() as s:
        result = s.execute(delete(NewsArticle).where(NewsArticle.published_at < cutoff))
        return result.rowcount or 0


# ─── Agent runs + suggestions (audit trail) ──────────────────────────────
def persist_agent_run(
    *,
    run_id: str,
    parent_run_id: str,
    symbol: str,
    agent: str,
    output: AgentOutput | None,
    inputs: dict[str, object],
) -> None:
    with get_session() as s:
        s.add(
            AgentRun(
                run_id=run_id,
                parent_run_id=parent_run_id,
                symbol=symbol,
                agent=agent,
                score=output.score if output else None,
                signal=output.signal if output else None,
                confidence=output.confidence if output else None,
                reasoning=output.reasoning if output else None,
                signals_used=json.dumps(output.signals_used) if output else None,
                inputs_hash=stable_hash(inputs),
                raw_output=output.model_dump_json() if output else None,
            )
        )


def persist_suggestion(parent_run_id: str, suggestion: Suggestion) -> None:
    with get_session() as s:
        s.add(
            SuggestionRow(
                parent_run_id=parent_run_id,
                symbol=suggestion.stock,
                as_of=datetime.fromisoformat(suggestion.as_of).replace(tzinfo=None),
                combined_score=suggestion.combined_score,
                combined_signal=suggestion.combined_signal,
                confidence=suggestion.confidence,
                reasoning=suggestion.reasoning,
                news_score=suggestion.news_score,
                news_signal=suggestion.news_signal,
                news_reasoning=suggestion.news_reasoning,
            )
        )


def latest_suggestions(limit: int = 50) -> list[SuggestionRow]:
    """Most recent N rows in chronological order (history, may contain dupes)."""
    with get_session() as s:
        q = select(SuggestionRow).order_by(SuggestionRow.as_of.desc()).limit(limit)
        return list(s.scalars(q))


def latest_suggestion_per_symbol() -> list[SuggestionRow]:
    """Return ONE row per symbol — the most recent suggestion for each stock.

    Uses a correlated subquery (works on SQLite). Sorted by combined_score desc.
    """
    with get_session() as s:
        # Per-symbol max(as_of)
        sub = (
            select(SuggestionRow.symbol, SuggestionRow.as_of)
            .order_by(SuggestionRow.symbol, SuggestionRow.as_of.desc())
            .subquery()
        )
        # SQLite-friendly: pull all rows, group in Python (cheap for ≤50 stocks)
        all_rows = list(
            s.scalars(select(SuggestionRow).order_by(SuggestionRow.as_of.desc()))
        )
        seen: set[str] = set()
        latest: list[SuggestionRow] = []
        for r in all_rows:
            if r.symbol in seen:
                continue
            seen.add(r.symbol)
            latest.append(r)
        latest.sort(key=lambda r: (r.combined_score or 0.0), reverse=True)
        return latest


def suggestions_for(symbol: str, limit: int = 30) -> list[SuggestionRow]:
    with get_session() as s:
        q = (
            select(SuggestionRow)
            .where(SuggestionRow.symbol == symbol)
            .order_by(SuggestionRow.as_of.desc())
            .limit(limit)
        )
        return list(s.scalars(q))
