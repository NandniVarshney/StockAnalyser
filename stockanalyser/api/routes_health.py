"""Health endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from stockanalyser import __version__
from stockanalyser.rovo_client import RovoClient

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, object]:
    return {"ok": True, "service": "stockanalyser", "version": __version__}


@router.get("/rovodev/health")
async def rovodev_health() -> dict[str, object]:
    client = RovoClient()
    ok = await client.health()
    return {"ok": ok, "rovodev_base_url": client.base_url}
