"""Analyze routes — trigger a fresh pipeline run."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from stockanalyser.agents import Suggestion
from stockanalyser.orchestrator import analyze_stock, analyze_watchlist

router = APIRouter(prefix="/analyze", tags=["analyze"])


@router.post("", response_model=list[Suggestion])
async def analyze_all() -> list[Suggestion]:
    """Run the full watchlist pipeline (synchronous, blocks until done)."""
    return await analyze_watchlist()


@router.post("/{symbol}", response_model=Suggestion)
async def analyze_one(symbol: str) -> Suggestion:
    try:
        return await analyze_stock(symbol.upper())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)) from e
