"""FastAPI app entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from stockanalyser import __version__
from stockanalyser.api.routes_analyze import router as analyze_router
from stockanalyser.api.routes_health import router as health_router
from stockanalyser.api.routes_sources import router as sources_router
from stockanalyser.api.routes_suggestions import router as suggestions_router
from stockanalyser.api.routes_watchlist import router as watchlist_router
from stockanalyser.config import load_watchlist
from stockanalyser.scheduler import start_scheduler, stop_scheduler
from stockanalyser.storage import init_db
from stockanalyser.storage.repositories import seed_watchlist
from stockanalyser.utils.logging import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hooks."""
    configure_logging()
    init_db()
    # Idempotent seed from YAML
    stocks = load_watchlist()
    seed_watchlist([s.model_dump() for s in stocks])
    start_scheduler()
    log.info("app_startup_complete", watchlist_size=len(stocks))
    try:
        yield
    finally:
        stop_scheduler()
        log.info("app_shutdown_complete")


app = FastAPI(
    title="StockAnalyser",
    version=__version__,
    description=(
        "Multi-agent Indian-NSE stock suggestion app (swing mode). "
        "Powered by local Rovo Dev CLI for LLM agents. "
        "Educational use only — not financial advice."
    ),
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(sources_router)
app.include_router(watchlist_router)
app.include_router(analyze_router)
app.include_router(suggestions_router)
