"""/sources/health — pings every external data provider once and reports status.

Phase 1 (Indian swing mode, free) data sources:
    market         - nselib (primary) + yfinance (fallback)
    fundamentals   - Screener.in (only — no fallback needed)
    news           - RSS feeds (Moneycontrol / ET / Livemint / Business Standard)
    agent runner   - local Rovo Dev CLI on :8766

This endpoint makes real network calls, so it's slower than /health (~3-8s).
Use for verification, not as a liveness probe.
"""

from __future__ import annotations

import re
import time
from datetime import date, timedelta
from typing import Any

import httpx
from fastapi import APIRouter

from stockanalyser.config import get_settings
from stockanalyser.providers.fundamentals.screener_provider import ScreenerProvider
from stockanalyser.providers.market.nselib_provider import NselibProvider
from stockanalyser.providers.market.yfinance_provider import YFinanceProvider
from stockanalyser.providers.news.rss_provider import RssNewsProvider

# Redact tokens / API keys from any error string before exposing it.
_REDACT_RE = re.compile(
    r"(?i)(token|apikey|api_key|key|secret|access[-_ ]token)=([A-Za-z0-9._\-]{8,})"
)


def _sanitise(msg: str) -> str:
    return _REDACT_RE.sub(r"\1=***REDACTED***", msg)


router = APIRouter(prefix="/sources", tags=["sources"])

# Use a well-known liquid stock for the probe.
PROBE_SYMBOL = "RELIANCE"


async def _timed(coro: Any) -> tuple[Any, float]:
    """Run an awaitable; return (result, elapsed_ms)."""
    t0 = time.perf_counter()
    result = await coro
    return result, round((time.perf_counter() - t0) * 1000, 1)


async def _check_market_nselib() -> dict[str, Any]:
    try:
        p = NselibProvider()
        end = date.today()
        start = end - timedelta(days=10)
        df, ms = await _timed(p.fetch_daily(PROBE_SYMBOL, start, end))
        return {
            "name": "nselib",
            "type": "market",
            "ok": not df.empty,
            "latency_ms": ms,
            "rows": int(len(df)),
            "note": f"last close: {df['close'].iloc[-1]}" if not df.empty else "empty",
        }
    except Exception as e:  # noqa: BLE001
        return {"name": "nselib", "type": "market", "ok": False, "error": _sanitise(str(e))[:200]}


async def _check_market_yfinance() -> dict[str, Any]:
    try:
        p = YFinanceProvider()
        end = date.today()
        start = end - timedelta(days=10)
        df, ms = await _timed(p.fetch_daily(PROBE_SYMBOL, start, end))
        return {
            "name": "yfinance",
            "type": "market",
            "ok": not df.empty,
            "latency_ms": ms,
            "rows": int(len(df)),
            "note": f"last close: {df['close'].iloc[-1]}" if not df.empty else "empty",
        }
    except Exception as e:  # noqa: BLE001
        return {"name": "yfinance", "type": "market", "ok": False, "error": _sanitise(str(e))[:200]}


async def _check_funda_screener() -> dict[str, Any]:
    try:
        p = ScreenerProvider()
        data, ms = await _timed(p.fetch(PROBE_SYMBOL))
        ok = data is not None and any(
            getattr(data, k, None) is not None for k in ("pe", "roe", "market_cap")
        )
        return {
            "name": "screener",
            "type": "fundamentals",
            "ok": ok,
            "latency_ms": ms,
            "note": (
                f"P/E={getattr(data, 'pe', None)}, ROE={getattr(data, 'roe', None)}"
                if ok
                else "no fields parsed"
            ),
        }
    except Exception as e:  # noqa: BLE001
        return {
            "name": "screener",
            "type": "fundamentals",
            "ok": False,
            "error": _sanitise(str(e))[:200],
        }


async def _check_news_rss() -> dict[str, Any]:
    try:
        p = RssNewsProvider()
        articles, ms = await _timed(p.fetch(PROBE_SYMBOL, days=7))
        sources = sorted({a.source for a in articles})
        return {
            "name": "rss",
            "type": "news",
            "ok": True,  # feeds reachable = healthy even if no articles match
            "latency_ms": ms,
            "articles": len(articles),
            "feeds_used": sources,
            "note": (
                f"{len(articles)} articles across {len(sources)} feeds"
                if articles
                else "feeds reachable, no matching articles in 7d"
            ),
        }
    except Exception as e:  # noqa: BLE001
        return {"name": "rss", "type": "news", "ok": False, "error": _sanitise(str(e))[:200]}


async def _check_rovo_cli() -> dict[str, Any]:
    base = get_settings().rovodev_base_url
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{base}/healthcheck")
        return {
            "name": "rovo_cli",
            "type": "agent_runner",
            "ok": r.status_code == 200,
            "latency_ms": round(r.elapsed.total_seconds() * 1000, 1),
            "note": f"{base}/healthcheck → {r.status_code}",
        }
    except Exception as e:  # noqa: BLE001
        return {
            "name": "rovo_cli",
            "type": "agent_runner",
            "ok": False,
            "error": f"{base} unreachable: {_sanitise(str(e))[:120]}",
        }


@router.get("/health")
async def sources_health() -> dict[str, Any]:
    """Ping every data source live. Returns one row per provider.

    Each check is wrapped in its own try/except so one provider crash never
    takes the whole endpoint down (which would otherwise 500 → empty body).
    """
    checks: list[dict[str, Any]] = []
    for name, fn in (
        ("nselib", _check_market_nselib),
        ("yfinance", _check_market_yfinance),
        ("screener", _check_funda_screener),
        ("rss", _check_news_rss),
        ("rovo_cli", _check_rovo_cli),
    ):
        try:
            checks.append(await fn())
        except Exception as e:  # noqa: BLE001
            checks.append(
                {
                    "name": name,
                    "ok": False,
                    "error": f"uncaught: {type(e).__name__}: {_sanitise(str(e))[:160]}",
                }
            )
    ok_count = sum(1 for c in checks if c.get("ok"))
    skipped = sum(1 for c in checks if c.get("skipped"))
    return {
        "summary": {
            "total": len(checks),
            "ok": ok_count,
            "failed": len(checks) - ok_count - skipped,
            "skipped": skipped,
        },
        "probe_symbol": PROBE_SYMBOL,
        "sources": checks,
    }
