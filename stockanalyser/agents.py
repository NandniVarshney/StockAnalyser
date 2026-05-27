"""Agent skill keys + shared Pydantic output schemas.

Each LLM agent (TA, FA, NS) is identified by a skill key matching a folder
under `.rovodev/subagents/<key>/SKILL.md`. The Rovo Dev CLI loads the markdown
and executes it as an agent against the inputs we send.

The aggregator is NOT an LLM — see `stockanalyser.aggregator`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SkillKey(StrEnum):
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    NEWS = "news"
    # Optional: only invoked if AGGREGATOR_USE_LLM_REASONING=true
    AGGREGATOR_REASONING = "aggregator-reasoning"


Signal = Literal["BUY", "HOLD", "SELL"]


class AgentOutput(BaseModel):
    """Strict contract every LLM agent must return as the final JSON block."""

    model_config = ConfigDict(extra="forbid")

    stock: str
    agent: Literal["technical", "fundamental", "news"]
    score: float = Field(ge=0, le=100)
    signal: Signal
    confidence: float = Field(ge=0, le=1)
    reasoning: str
    signals_used: list[str] = Field(default_factory=list)
    data_freshness: str | None = None  # ISO-8601


class Suggestion(BaseModel):
    """Final per-stock suggestion returned to API clients."""

    model_config = ConfigDict(extra="forbid")

    stock: str
    as_of: str  # ISO-8601 IST

    combined_score: float
    combined_signal: Signal
    confidence: float
    reasoning: str

    news_score: float | None
    news_signal: Signal | None
    news_reasoning: str | None

    agents: dict[str, AgentOutput | None]

    disclaimer: str = "Educational use only. Not financial advice."
