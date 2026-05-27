"""Watchlist routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from stockanalyser.config import load_watchlist
from stockanalyser.storage.repositories import list_watchlist, seed_watchlist

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("")
def get_watchlist() -> list[dict[str, object]]:
    rows = list_watchlist(active_only=True)
    return [
        {"symbol": r.symbol, "name": r.company_name, "sector": r.sector, "active": r.active}
        for r in rows
    ]


@router.post("/reload")
def reload_from_yaml() -> dict[str, object]:
    """Re-sync the watchlist table from config/watchlist.yaml."""
    stocks = load_watchlist()
    seed_watchlist([s.model_dump() for s in stocks])
    return {"ok": True, "count": len(stocks)}


@router.delete("/{symbol}")
def deactivate(symbol: str) -> dict[str, object]:
    rows = list_watchlist(active_only=False)
    for r in rows:
        if r.symbol == symbol:
            # We don't strictly delete — just flip `active` via a fresh seed.
            # For Phase 1, keep it simple: error out and ask user to edit YAML.
            raise HTTPException(
                status_code=400,
                detail=(
                    "Phase 1: edit config/watchlist.yaml and POST /watchlist/reload "
                    "to remove/add stocks."
                ),
            )
    raise HTTPException(status_code=404, detail=f"symbol {symbol} not found")
