"""Technical-indicator computation (pandas-ta-classic).

Computed deterministically in Python and PUSHED to the Technical agent as part
of its inputs (the agent does NOT compute indicators itself — that keeps the
prompt small and the score reproducible).
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pandas_ta_classic as ta  # type: ignore[import-untyped]


def compute_indicators(ohlcv: pd.DataFrame) -> dict[str, Any]:
    """Return a dict of the latest indicator values + a small slice of history.

    Output schema (what we send to the TA skill):
        {
          "as_of_close":  120.45,
          "rsi_14":       62.0,
          "macd":         {"macd": 1.2, "signal": 0.8, "hist": 0.4},
          "bollinger":    {"lower": 110.0, "mid": 118.0, "upper": 126.0},
          "sma":          {"sma20": 118, "sma50": 115, "sma200": 110},
          "atr_14":       2.5,
          "volume":       {"latest": 1234567, "avg20": 1100000, "ratio": 1.12}
        }
    """
    if ohlcv.empty:
        return {}

    df = ohlcv.copy().sort_values("date").reset_index(drop=True)

    df["rsi_14"] = ta.rsi(df["close"], length=14)
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd is not None and not macd.empty:
        df = df.join(macd)
    bb = ta.bbands(df["close"], length=20, std=2)
    if bb is not None and not bb.empty:
        df = df.join(bb)
    df["sma20"] = ta.sma(df["close"], length=20)
    df["sma50"] = ta.sma(df["close"], length=50)
    df["sma200"] = ta.sma(df["close"], length=200)
    df["atr_14"] = ta.atr(df["high"], df["low"], df["close"], length=14)
    df["vol_avg20"] = df["volume"].rolling(window=20, min_periods=1).mean()

    last = df.iloc[-1]

    def _round(v: object, n: int = 2) -> float | None:
        return None if pd.isna(v) else round(float(v), n)  # type: ignore[arg-type]

    return {
        "as_of_close": _round(last["close"]),
        "rsi_14": _round(last.get("rsi_14")),
        "macd": {
            "macd": _round(last.get("MACD_12_26_9")),
            "signal": _round(last.get("MACDs_12_26_9")),
            "hist": _round(last.get("MACDh_12_26_9")),
        },
        "bollinger": {
            "lower": _round(last.get("BBL_20_2.0")),
            "mid": _round(last.get("BBM_20_2.0")),
            "upper": _round(last.get("BBU_20_2.0")),
        },
        "sma": {
            "sma20": _round(last.get("sma20")),
            "sma50": _round(last.get("sma50")),
            "sma200": _round(last.get("sma200")),
        },
        "atr_14": _round(last.get("atr_14")),
        "volume": {
            "latest": int(last["volume"]) if not pd.isna(last["volume"]) else None,
            "avg20": int(last["vol_avg20"]) if not pd.isna(last["vol_avg20"]) else None,
            "ratio": _round(last["volume"] / last["vol_avg20"]) if last["vol_avg20"] else None,
        },
    }
