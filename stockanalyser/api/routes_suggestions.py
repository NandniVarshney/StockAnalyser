"""Suggestion + agent-runs routes — read-only history."""

from __future__ import annotations

from fastapi import APIRouter

from stockanalyser.storage.repositories import latest_suggestions, suggestions_for

router = APIRouter(tags=["suggestions"])


def _row_to_dict(r: object) -> dict[str, object]:
    return {
        "parent_run_id": r.parent_run_id,  # type: ignore[attr-defined]
        "symbol": r.symbol,  # type: ignore[attr-defined]
        "as_of": r.as_of.isoformat(),  # type: ignore[attr-defined]
        "combined_score": r.combined_score,  # type: ignore[attr-defined]
        "combined_signal": r.combined_signal,  # type: ignore[attr-defined]
        "confidence": r.confidence,  # type: ignore[attr-defined]
        "reasoning": r.reasoning,  # type: ignore[attr-defined]
        "news_score": r.news_score,  # type: ignore[attr-defined]
        "news_signal": r.news_signal,  # type: ignore[attr-defined]
        "news_reasoning": r.news_reasoning,  # type: ignore[attr-defined]
    }


@router.get("/suggestions")
def get_latest_suggestions(limit: int = 50) -> list[dict[str, object]]:
    return [_row_to_dict(r) for r in latest_suggestions(limit=limit)]


@router.get("/suggestions/{symbol}")
def get_history(symbol: str, limit: int = 30) -> list[dict[str, object]]:
    return [_row_to_dict(r) for r in suggestions_for(symbol.upper(), limit=limit)]
