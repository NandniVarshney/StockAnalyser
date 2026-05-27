"""Abstract provider interfaces.

Each provider must be safe to call concurrently. They are the ONLY layer that
talks to external APIs — orchestrator, agents, and aggregator never touch the
network.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd


# ─── DTOs ────────────────────────────────────────────────────────────────
@dataclass
class FundamentalsDTO:
    symbol: str
    fetched_at: datetime
    source: str
    pe: float | None = None
    pb: float | None = None
    roe: float | None = None
    roce: float | None = None
    debt_equity: float | None = None
    eps: float | None = None
    market_cap: float | None = None
    revenue_yoy: float | None = None
    profit_yoy: float | None = None
    raw: dict[str, Any] | None = None


@dataclass
class NewsArticleDTO:
    symbol: str
    source: str
    title: str
    url: str
    summary: str | None
    published_at: datetime


# ─── Interfaces ──────────────────────────────────────────────────────────
class MarketDataProvider(ABC):
    """Daily OHLCV. Phase 1 = swing mode (no intraday)."""

    name: str = "abstract"

    @abstractmethod
    async def fetch_daily(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Return DataFrame with columns: date, open, high, low, close, volume."""


class FundamentalsProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    async def fetch(self, symbol: str) -> FundamentalsDTO:
        ...


class NewsProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    async def fetch(self, symbol: str, days: int = 7) -> list[NewsArticleDTO]:
        ...
