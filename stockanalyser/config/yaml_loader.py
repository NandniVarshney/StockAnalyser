"""YAML loaders for watchlist, weights, and source routing.

These are kept separate from `Settings` because they're domain configuration
(not secrets) and are easier to edit as YAML.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator

# ─── Config-file location ─────────────────────────────────────────────────
_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


# ─── Schemas ──────────────────────────────────────────────────────────────
class Stock(BaseModel):
    symbol: str
    name: str
    sector: str


class Weights(BaseModel):
    technical: float = Field(ge=0, le=1)
    fundamental: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _sum_to_one(self) -> "Weights":
        total = self.technical + self.fundamental
        if not (0.999 <= total <= 1.001):
            raise ValueError(f"weights must sum to 1.0 (got {total})")
        return self


class Thresholds(BaseModel):
    buy: int = Field(ge=0, le=100)
    sell: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _ordered(self) -> "Thresholds":
        if self.sell >= self.buy:
            raise ValueError(f"sell ({self.sell}) must be < buy ({self.buy})")
        return self


class WeightsConfig(BaseModel):
    weights: Weights
    thresholds: Thresholds
    news_thresholds: dict[str, int]


# ─── Loaders ──────────────────────────────────────────────────────────────
def _read_yaml(name: str) -> dict[str, Any]:
    path = _CONFIG_DIR / name
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)  # type: ignore[no-any-return]


def load_watchlist() -> list[Stock]:
    raw = _read_yaml("watchlist.yaml")
    return [Stock(**s) for s in raw.get("stocks", [])]


def load_weights() -> WeightsConfig:
    return WeightsConfig(**_read_yaml("weights.yaml"))


def load_sources() -> dict[str, Any]:
    return _read_yaml("sources.yaml")
