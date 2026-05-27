"""Deterministic aggregator — pure Python, no LLM call.

combined_score = w_ta * TA.score + w_fa * FA.score
news_score is kept SEPARATE (not folded into combined_score).

If one of (TA, FA) is missing/failed, we degrade gracefully:
  - re-normalise weights over what we have
  - lower confidence by 40%
  - note the missing agent in the reasoning
"""

from __future__ import annotations

from stockanalyser.agents import AgentOutput, Signal, Suggestion
from stockanalyser.config.yaml_loader import Thresholds, Weights
from stockanalyser.utils.time import isoformat


def signal_from_score(score: float, thresholds: Thresholds) -> Signal:
    if score >= thresholds.buy:
        return "BUY"
    if score < thresholds.sell:
        return "SELL"
    return "HOLD"


def news_signal_from_score(score: float, positive: int, negative: int) -> Signal:
    if score >= positive:
        return "BUY"
    if score < negative:
        return "SELL"
    return "HOLD"


def aggregate(
    symbol: str,
    technical: AgentOutput | None,
    fundamental: AgentOutput | None,
    news: AgentOutput | None,
    weights: Weights,
    thresholds: Thresholds,
    news_thresholds: dict[str, int],
) -> Suggestion:
    """Combine TA + FA into a final suggestion. News reported separately."""

    # ─── combined score (TA + FA only) ────────────────────────────────────
    available: list[tuple[float, float, AgentOutput]] = []
    if technical is not None:
        available.append((weights.technical, technical.score, technical))
    if fundamental is not None:
        available.append((weights.fundamental, fundamental.score, fundamental))

    if not available:
        # No LLM agents responded — emit a "no-call" suggestion.
        return Suggestion(
            stock=symbol,
            as_of=isoformat(),
            combined_score=0.0,
            combined_signal="HOLD",
            confidence=0.0,
            reasoning="Both Technical and Fundamental agents failed. No call.",
            news_score=news.score if news else None,
            news_signal=(news.signal if news else None),
            news_reasoning=(news.reasoning if news else None),
            agents={"technical": None, "fundamental": None, "news": news},
        )

    weight_sum = sum(w for w, _, _ in available)
    combined = sum(w * s for w, s, _ in available) / weight_sum
    combined_signal = signal_from_score(combined, thresholds)

    # ─── confidence ───────────────────────────────────────────────────────
    confs = [a.confidence for _, _, a in available]
    base_conf = min(confs)
    missing_count = 2 - len(available)
    confidence = base_conf * (1.0 - 0.4 * missing_count)

    # ─── reasoning (template; LLM polish is optional/Phase 2) ─────────────
    parts = [
        f"Combined score {combined:.0f} → {combined_signal} "
        f"(buy≥{thresholds.buy}, sell<{thresholds.sell})."
    ]
    if technical:
        parts.append(f"TA={technical.score:.0f} ({technical.signal}).")
    if fundamental:
        parts.append(f"FA={fundamental.score:.0f} ({fundamental.signal}).")
    if missing_count:
        parts.append(f"NOTE: {missing_count} agent(s) unavailable; confidence reduced.")
    reasoning = " ".join(parts)

    # ─── news (separate) ──────────────────────────────────────────────────
    news_score = news.score if news else None
    news_signal_val: Signal | None = (
        news_signal_from_score(
            news.score,
            news_thresholds.get("positive", 60),
            news_thresholds.get("negative", 40),
        )
        if news
        else None
    )

    return Suggestion(
        stock=symbol,
        as_of=isoformat(),
        combined_score=round(combined, 2),
        combined_signal=combined_signal,
        confidence=round(confidence, 2),
        reasoning=reasoning,
        news_score=round(news_score, 2) if news_score is not None else None,
        news_signal=news_signal_val,
        news_reasoning=news.reasoning if news else None,
        agents={"technical": technical, "fundamental": fundamental, "news": news},
    )
