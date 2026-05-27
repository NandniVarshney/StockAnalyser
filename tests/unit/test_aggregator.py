"""Aggregator behaviour — happy paths + degraded paths."""

from __future__ import annotations

from stockanalyser.agents import AgentOutput
from stockanalyser.aggregator import aggregate
from stockanalyser.config.yaml_loader import Thresholds, Weights


def _agent(name: str, score: float, signal: str, conf: float = 0.8) -> AgentOutput:
    return AgentOutput(
        stock="RELIANCE",
        agent=name,
        score=score,
        signal=signal,
        confidence=conf,
        reasoning="...",
        signals_used=[],
    )


_WEIGHTS = Weights(technical=0.4, fundamental=0.6)
_THRESH = Thresholds(buy=70, sell=40)
_NEWS_TH = {"positive": 60, "negative": 40}


def test_buy_when_both_strong() -> None:
    s = aggregate(
        "RELIANCE",
        _agent("technical", 75, "BUY"),
        _agent("fundamental", 80, "BUY"),
        _agent("news", 65, "BUY"),
        _WEIGHTS, _THRESH, _NEWS_TH,
    )
    assert s.combined_signal == "BUY"
    assert s.combined_score == 78.0  # 0.4*75 + 0.6*80
    assert s.news_signal == "BUY"


def test_sell_when_both_weak() -> None:
    s = aggregate(
        "RELIANCE",
        _agent("technical", 30, "SELL"),
        _agent("fundamental", 25, "SELL"),
        None,
        _WEIGHTS, _THRESH, _NEWS_TH,
    )
    assert s.combined_signal == "SELL"
    assert s.news_score is None


def test_degraded_when_one_agent_missing() -> None:
    s = aggregate(
        "RELIANCE",
        None,
        _agent("fundamental", 80, "BUY"),
        None,
        _WEIGHTS, _THRESH, _NEWS_TH,
    )
    assert s.combined_signal == "BUY"
    assert s.combined_score == 80.0           # FA alone (re-normalised)
    assert s.confidence < 0.8                  # penalised
    assert "unavailable" in s.reasoning.lower()


def test_no_call_when_both_missing() -> None:
    s = aggregate("RELIANCE", None, None, None, _WEIGHTS, _THRESH, _NEWS_TH)
    assert s.combined_signal == "HOLD"
    assert s.confidence == 0.0
