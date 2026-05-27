"""IST time helpers."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from stockanalyser.config import get_settings


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def now_ist() -> datetime:
    return datetime.now(tz())


def today_ist() -> date:
    return now_ist().date()


def isoformat(dt: datetime | None = None) -> str:
    return (dt or now_ist()).isoformat()
