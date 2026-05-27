"""Sanity checks on YAML configs."""

from __future__ import annotations

from stockanalyser.config import load_sources, load_watchlist, load_weights


def test_watchlist_loads() -> None:
    stocks = load_watchlist()
    assert len(stocks) > 0
    assert all(s.symbol and s.name and s.sector for s in stocks)


def test_weights_sum_to_one() -> None:
    cfg = load_weights()
    assert abs(cfg.weights.technical + cfg.weights.fundamental - 1.0) < 1e-6
    assert cfg.thresholds.sell < cfg.thresholds.buy


def test_sources_have_primary() -> None:
    src = load_sources()
    assert src["market_data"]["primary"] == "nselib"
    assert "rss_feeds" in src
    assert all("url" in f and "source" in f for f in src["rss_feeds"])
