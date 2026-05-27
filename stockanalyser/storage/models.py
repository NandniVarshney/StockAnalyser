"""SQLAlchemy ORM models — matches schema in PLAN.md §6."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class WatchlistRow(Base):
    __tablename__ = "watchlist"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(80))
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    active: Mapped[bool] = mapped_column(default=True)


class FundamentalsCache(Base):
    __tablename__ = "fundamentals_cache"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    pe: Mapped[float | None] = mapped_column(Float)
    pb: Mapped[float | None] = mapped_column(Float)
    roe: Mapped[float | None] = mapped_column(Float)
    roce: Mapped[float | None] = mapped_column(Float)
    debt_equity: Mapped[float | None] = mapped_column(Float)
    eps: Mapped[float | None] = mapped_column(Float)
    market_cap: Mapped[float | None] = mapped_column(Float)
    revenue_yoy: Mapped[float | None] = mapped_column(Float)
    profit_yoy: Mapped[float | None] = mapped_column(Float)
    raw_json: Mapped[str | None] = mapped_column(Text)


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256(url)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("idx_news_symbol_time", "symbol", "published_at"),)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    parent_run_id: Mapped[str | None] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    agent: Mapped[str] = mapped_column(String(30), nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    signal: Mapped[str | None] = mapped_column(String(10))
    confidence: Mapped[float | None] = mapped_column(Float)
    reasoning: Mapped[str | None] = mapped_column(Text)
    signals_used: Mapped[str | None] = mapped_column(Text)   # JSON array
    inputs_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    raw_output: Mapped[str | None] = mapped_column(Text)      # full JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SuggestionRow(Base):
    __tablename__ = "suggestions"

    parent_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    combined_score: Mapped[float] = mapped_column(Float, nullable=False)
    combined_signal: Mapped[str] = mapped_column(String(10), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text)
    news_score: Mapped[float | None] = mapped_column(Float)
    news_signal: Mapped[str | None] = mapped_column(String(10))
    news_reasoning: Mapped[str | None] = mapped_column(Text)
    weights_json: Mapped[str | None] = mapped_column(Text)
    thresholds_json: Mapped[str | None] = mapped_column(Text)
