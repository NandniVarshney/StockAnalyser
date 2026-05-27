"""Map our canonical NSE symbol to provider-specific tickers."""

from __future__ import annotations


def to_yfinance(symbol: str) -> str:
    """RELIANCE -> RELIANCE.NS"""
    return symbol if symbol.endswith(".NS") else f"{symbol}.NS"


def to_nselib(symbol: str) -> str:
    """nselib uses the bare NSE symbol."""
    return symbol.removesuffix(".NS")


def to_finnhub(symbol: str) -> str:
    """Finnhub uses {SYMBOL}.NS for Indian stocks."""
    return symbol if symbol.endswith(".NS") else f"{symbol}.NS"


def to_screener_slug(symbol: str) -> str:
    """Screener.in URL slug — lower-case bare symbol."""
    return symbol.removesuffix(".NS").lower()
