"""StockAnalyser dashboard — a minimal Streamlit UI over the FastAPI suggestions.

Run with:
    make dashboard          # → http://localhost:8501

Requires the FastAPI app to be running (`make api`).
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx
import pandas as pd
import streamlit as st

API_BASE = os.environ.get("STOCKANALYSER_API", "http://localhost:8000")
REFRESH_SECONDS = 30

# ─── Page setup ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="StockAnalyser",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ─── Helpers ───────────────────────────────────────────────────────────────
def _signal_color(signal: str | None) -> str:
    return {"BUY": "#16a34a", "SELL": "#dc2626", "HOLD": "#f59e0b"}.get(signal or "", "#6b7280")


def _signal_emoji(signal: str | None) -> str:
    return {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}.get(signal or "", "⚪")


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def fetch_json(path: str) -> Any:
    with httpx.Client(timeout=10.0) as c:
        r = c.get(f"{API_BASE}{path}")
        r.raise_for_status()
        return r.json()


def post_json(path: str) -> Any:
    """Trigger an analysis. Not cached — always hits the API."""
    with httpx.Client(timeout=600.0) as c:
        r = c.post(f"{API_BASE}{path}")
        r.raise_for_status()
        return r.json()


# ─── Sidebar ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 StockAnalyser")
    st.caption("Swing-mode suggestions for Indian NSE")
    st.divider()

    # Health
    try:
        health = fetch_json("/health")
        rovo = fetch_json("/rovodev/health")
        st.metric("FastAPI", "✅ up" if health.get("ok") else "❌ down")
        st.metric("Rovo CLI", "✅ up" if rovo.get("ok") else "❌ down")
    except Exception as e:
        st.error(f"API not reachable at {API_BASE}\n\n{e}")
        st.stop()

    st.divider()

    # Watchlist + trigger
    try:
        watchlist = fetch_json("/watchlist")
        symbols = [s["symbol"] for s in watchlist]
    except Exception:
        watchlist, symbols = [], []

    selected = st.selectbox("Pick a stock", ["— all —"] + symbols)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Refresh"):
            st.cache_data.clear()
            st.rerun()
    with col2:
        if st.button("⚡ Analyse"):
            with st.spinner("Running pipeline..."):
                target = "/analyze" if selected == "— all —" else f"/analyze/{selected}"
                post_json(target)
            st.cache_data.clear()
            st.rerun()

    st.caption(f"Auto-refresh: {REFRESH_SECONDS}s\nAPI: `{API_BASE}`")


# ─── Main view ─────────────────────────────────────────────────────────────
st.title("Today's Suggestions")
st.caption("Educational use only. Not financial advice.")

try:
    suggestions = fetch_json("/suggestions")
except Exception as e:
    st.error(f"Couldn't load /suggestions: {e}")
    st.stop()

if not suggestions:
    st.info("No suggestions yet. Click **⚡ Analyse** in the sidebar to run the pipeline.")
    st.stop()

# Defensive de-dupe: keep only the LATEST row per symbol (in case the API
# ever returns history). The API already does this, but better safe.
_seen: set[str] = set()
_latest: list[dict[str, Any]] = []
for s in sorted(suggestions, key=lambda r: r.get("as_of", ""), reverse=True):
    sym = s.get("symbol")
    if sym in _seen:
        continue
    _seen.add(sym)
    _latest.append(s)
suggestions = _latest

# Filter to one stock if selected
if selected != "— all —":
    suggestions = [s for s in suggestions if s.get("symbol") == selected]

# Sort by combined_score descending
suggestions = sorted(suggestions, key=lambda r: r.get("combined_score", 0) or 0, reverse=True)

# ─── Summary bar ──────────────────────────────────────────────────────────
buys = sum(1 for s in suggestions if s.get("combined_signal") == "BUY")
sells = sum(1 for s in suggestions if s.get("combined_signal") == "SELL")
holds = sum(1 for s in suggestions if s.get("combined_signal") == "HOLD")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Stocks", len(suggestions))
c2.metric("🟢 BUY", buys)
c3.metric("🟡 HOLD", holds)
c4.metric("🔴 SELL", sells)

st.divider()

# ─── Per-stock cards ──────────────────────────────────────────────────────
for s in suggestions:
    color = _signal_color(s.get("combined_signal"))
    emoji = _signal_emoji(s.get("combined_signal"))
    score = s.get("combined_score", 0) or 0
    conf = s.get("confidence", 0) or 0

    with st.container(border=True):
        head = st.columns([3, 1, 1, 1])
        head[0].markdown(f"### {emoji} {s['symbol']}")
        head[1].metric("Score", f"{score:.1f}")
        head[2].metric("Signal", s.get("combined_signal") or "—")
        head[3].metric("Confidence", f"{conf:.0%}")

        st.progress(min(max(score / 100.0, 0.0), 1.0))
        st.caption(s.get("reasoning", ""))

        # News (separate signal)
        news_score = s.get("news_score")
        if news_score is not None:
            news_color = _signal_color(s.get("news_signal"))
            st.markdown(
                f"**News** {_signal_emoji(s.get('news_signal'))} "
                f"<span style='color:{news_color}'>"
                f"{news_score:.1f} · {s.get('news_signal')}"
                f"</span>",
                unsafe_allow_html=True,
            )
            st.caption(s.get("news_reasoning", ""))

        # History — last N runs for this stock
        with st.expander(f"History · {s['symbol']}"):
            try:
                history = fetch_json(f"/suggestions/{s['symbol']}")
                if history:
                    df_hist = pd.DataFrame(history)[
                        ["as_of", "combined_score", "combined_signal", "confidence", "news_score"]
                    ]
                    st.dataframe(df_hist, use_container_width=True, hide_index=True)
                else:
                    st.caption("No history yet.")
            except Exception as e:  # noqa: BLE001
                st.caption(f"(couldn't fetch history: {e})")

        # As-of timestamp
        as_of = s.get("as_of")
        if as_of:
            try:
                ts = datetime.fromisoformat(as_of).strftime("%d %b %Y, %H:%M %Z")
                st.caption(f"_as of {ts}_")
            except Exception:
                st.caption(f"_as of {as_of}_")

st.divider()
st.caption(
    "Combined score = `0.4 × Technical + 0.6 × Fundamental` "
    "(weights/thresholds configurable in `config/weights.yaml`). News kept separate."
)
