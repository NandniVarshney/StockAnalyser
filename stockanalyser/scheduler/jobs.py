"""APScheduler jobs — swing-mode daily pipeline.

Schedule (IST):
    22:00  ingest_fundamentals     (24h-cached → mostly no-op)
    03:00  cleanup_news            (purge >30d)
    07:30  ingest_ohlcv_daily      (append yesterday's candle)
    07:45  ingest_news             (last 7d, dedupe)
    08:30  run_analysis            (3 agents + aggregator → suggestions)
"""

from __future__ import annotations

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from stockanalyser.config import get_settings, load_watchlist
from stockanalyser.orchestrator import analyze_watchlist
from stockanalyser.providers.fundamentals import FundamentalsFacade
from stockanalyser.providers.market import MarketDataFacade
from stockanalyser.providers.news import NewsFacade
from stockanalyser.storage.repositories import purge_old_news
from stockanalyser.utils.logging import get_logger

log = get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None


# ─── Jobs ────────────────────────────────────────────────────────────────
async def job_ingest_fundamentals() -> None:
    facade = FundamentalsFacade()
    for s in load_watchlist():
        try:
            await facade.get(s.symbol)
        except Exception as e:  # noqa: BLE001
            log.warning("ingest_fundamentals_failed", symbol=s.symbol, error=str(e))


async def job_ingest_ohlcv_daily() -> None:
    facade = MarketDataFacade()
    for s in load_watchlist():
        try:
            await facade.get_daily(s.symbol)
        except Exception as e:  # noqa: BLE001
            log.warning("ingest_ohlcv_failed", symbol=s.symbol, error=str(e))


async def job_ingest_news() -> None:
    facade = NewsFacade()
    for s in load_watchlist():
        try:
            await facade.refresh_and_get(s.symbol)
        except Exception as e:  # noqa: BLE001
            log.warning("ingest_news_failed", symbol=s.symbol, error=str(e))


async def job_cleanup_news() -> None:
    deleted = purge_old_news()
    log.info("cleanup_news_done", deleted=deleted)


async def job_run_analysis() -> None:
    log.info("daily_analysis_start")
    results = await analyze_watchlist()
    log.info("daily_analysis_done", count=len(results))


# ─── Lifecycle ───────────────────────────────────────────────────────────
def register_jobs(scheduler: AsyncIOScheduler) -> None:
    tz = get_settings().timezone

    scheduler.add_job(
        job_ingest_fundamentals,
        CronTrigger(hour=22, minute=0, timezone=tz),
        id="ingest_fundamentals",
        replace_existing=True,
    )
    scheduler.add_job(
        job_cleanup_news,
        CronTrigger(hour=3, minute=0, timezone=tz),
        id="cleanup_news",
        replace_existing=True,
    )
    scheduler.add_job(
        job_ingest_ohlcv_daily,
        CronTrigger(hour=7, minute=30, timezone=tz),
        id="ingest_ohlcv_daily",
        replace_existing=True,
    )
    scheduler.add_job(
        job_ingest_news,
        CronTrigger(hour=7, minute=45, timezone=tz),
        id="ingest_news",
        replace_existing=True,
    )
    scheduler.add_job(
        job_run_analysis,
        CronTrigger(hour=8, minute=30, timezone=tz),
        id="run_analysis",
        replace_existing=True,
    )


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        settings = get_settings()
        _scheduler = AsyncIOScheduler(
            jobstores={"default": SQLAlchemyJobStore(url=f"sqlite:///{settings.sqlite_path}")},
            timezone=settings.timezone,
        )
        register_jobs(_scheduler)
        _scheduler.start()
        log.info("scheduler_started", jobs=[j.id for j in _scheduler.get_jobs()])
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("scheduler_stopped")
