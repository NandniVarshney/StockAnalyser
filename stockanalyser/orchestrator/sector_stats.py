"""Sector medians for fundamentals z-scoring."""

from __future__ import annotations

import statistics
from typing import Iterable

from stockanalyser.providers.base import FundamentalsDTO

_FIELDS = ("pe", "pb", "roe", "roce", "debt_equity", "eps", "revenue_yoy", "profit_yoy")


def compute_sector_medians(
    fundas: Iterable[tuple[str, FundamentalsDTO]],
) -> dict[str, dict[str, float]]:
    """Group by sector → per-field median (skipping NaNs).

    Args:
        fundas: iterable of (sector, FundamentalsDTO).

    Returns:
        {sector: {field: median_value}}
    """
    buckets: dict[str, dict[str, list[float]]] = {}
    for sector, dto in fundas:
        b = buckets.setdefault(sector, {f: [] for f in _FIELDS})
        for f in _FIELDS:
            v = getattr(dto, f, None)
            if v is not None:
                b[f].append(float(v))

    return {
        sector: {f: round(statistics.median(values), 4) for f, values in fields.items() if values}
        for sector, fields in buckets.items()
    }
