# 🚀 StockAnalyser — Quick Pitch

**What it is:** A multi-agent app that analyses Indian (NSE) stocks and outputs **buy / hold / sell** suggestions with confidence scores and human-readable reasoning. **Swing-trading mode only** (daily timeframe — no intraday), **single user**, one analysis run per day, before market opens. Built as an MVP for testing, productionised later.

**Why it's different:** Most stock apps either give you raw data or a single black-box "score". We split the analysis into **specialised AI agents** (technical, fundamental, news), each producing its own structured opinion. A deterministic aggregator combines technical + fundamental into one combined score, while keeping news as a separate signal — so we can see *where* the signals agree or diverge.

---

## 🏗️ Architecture (1-screen view)

**Glossary (so the diagram is unambiguous):**
- **Skill** = a markdown file in our git repo (`.rovodev/subagents/<name>/SKILL.md`) holding the agent's prompt + JSON output contract.
- **Agent** = the Rovo Dev CLI **executing that skill** with the inputs we send it. Lives *inside* the Rovo server.
- **Orchestrator** = our Python that gathers data and calls the Rovo server (push pattern — sends full payloads, skills never read disk/DB).
- **Aggregator** = pure Python function that combines TA + FA scores. **No LLM**.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  1. External Data Sources (free Indian APIs, daily-only)                 │
│     nselib (daily) · yfinance (fallback) · Screener.in ·                 │
│     Finnhub · RSS (Moneycontrol/ET/Livemint) · NewsData                  │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │ fetch raw data
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  StockAnalyser  —  Python / FastAPI (port 8000, runs on your laptop)     │
│                                                                          │
│   ┌──────────────────┐                                                   │
│   │ 2. Data Providers│  the ONLY layer that talks to external APIs       │
│   │   (read cache    │  Cache-first: only fetch yesterday's new candle,  │
│   │    first, fetch  │  reuse fundamentals for 24h, dedupe news by URL   │
│   │    delta only)   │                                                   │
│   └────────┬─────────┘                                                   │
│            │ raw OHLCV / fundamentals / news (in-memory)                 │
│            ▼                                                             │
│   ┌──────────────────────────────────────────────────────┐               │
│   │ 3. Orchestrator (once-a-day pre-market pipeline)     │               │
│   │   a) compute indicators (RSI, MACD, SMA200, …)       │               │
│   │   b) compute sector medians                          │               │
│   │   c) build SELF-CONTAINED payload per agent          │               │
│   │   d) persist copy to SQLite/Parquet (audit) ──┐      │               │
│   │   e) POST to Rovo server (3 parallel calls)   │      │               │
│   └──────┬────────────────────────────────────────│──────┘               │
│          │                                        ▼                      │
│          │                              ┌────────────────┐               │
│          │                              │ SQLite +       │               │
│          │ 4. POST to Rovo with         │ Parquet        │ (write only — │
│          │    FULL inputs per call      │ (audit trail)  │  skills don't │
│          │    (push pattern)            └────────────────┘  read this)   │
└──────────│──────────────────────────────────────────────────────────────┘
           │
           ▼ HTTP + SSE
┌──────────────────────────────────────────────────────────┐
│  acli rovodev serve (port 8766) — local Rovo Dev CLI     │
│                                                          │
│   Loads our skill files and runs them as agents.         │
│   NO Atlassian MCP tools attached. Agents see ONLY the   │
│   structured payload we send them.                       │
│                                                          │
│     ┌───────────┐ ┌───────────┐ ┌───────────┐            │
│     │ Technical │ │Fundamental│ │   News    │            │
│     │   Agent   │ │   Agent   │ │   Agent   │            │
│     │  reads:   │ │  reads:   │ │  reads:   │            │
│     │ technical/│ │fundamental│ │   news/   │            │
│     │  SKILL.md │ │  /SKILL.md│ │  SKILL.md │            │
│     └─────┬─────┘ └─────┬─────┘ └─────┬─────┘            │
│           │ JSON        │ JSON        │ JSON             │
└───────────┼─────────────┼─────────────┼──────────────────┘
            │ 5. each agent returns {score, signal, confidence, reasoning}
            ▼             ▼             ▼
┌──────────────────────────────────────────────────────────┐
│  back in StockAnalyser FastAPI                           │
│                                                          │
│   ┌─────────────────────────────────────────────┐        │
│   │ 6. Aggregator  —  pure Python, NO LLM       │        │
│   │    combined = wTA·TA + wFA·FA               │        │
│   │    threshold → BUY / HOLD / SELL            │        │
│   │    news_score kept separate                 │        │
│   └────────────────────┬────────────────────────┘        │
│                        ▼                                 │
│   ┌─────────────────────────────────────────────┐        │
│   │ 7. REST API → final JSON suggestion         │        │
│   │    GET /suggestions  POST /analyze          │        │
│   └─────────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────────┘

How to read it: 1 → 2 → 3 → 4 (POST to Rovo) → 5 (JSON back) → 6 → 7.
```

---

## 🧠 The 4 Agents

| Agent | What it reads | What it outputs |
|---|---|---|
| **1. Technical** | OHLCV + indicators (RSI, MACD, Bollinger, SMA50/200, volume) | Score 0–100, signal, reasoning ("MACD bullish crossover, RSI 62, above 200DMA") |
| **2. Fundamental** | P/E, ROE, ROCE, debt/equity, EPS, revenue/profit growth vs sector medians | Score 0–100, reasoning ("ROE 18% vs sector 12%; D/E elevated") |
| **3. News** | Last 7 days of news per stock, LLM-scored sentiment with recency decay | News score 0–100 + top 3 catalysts + top 3 risks |
| **4. Aggregator** | Outputs of agents 1 + 2 (NOT news) | `combined_score = 0.4·TA + 0.6·FA`, threshold → BUY/HOLD/SELL, confidence |

**Final JSON example:**
```json
{
  "stock": "RELIANCE",
  "combined_score": 72, "combined_signal": "BUY", "confidence": 0.81,
  "reasoning": "Above BUY threshold. Strong ROE offsets overbought RSI.",
  "news_score": 55, "news_signal": "HOLD",
  "news_reasoning": "Mixed: positive Jio earnings vs regulatory concerns."
}
```

---

## 🛠️ Tech Stack (TL;DR)

| Layer | Choice | Why |
|---|---|---|
| **Language** | Python 3.11 | Best ecosystem for finance + ML + agents |
| **AI agents** | **Rovo Dev CLI** (`acli rovodev serve` on :8766) | Atlassian's local agent server — we write agent prompts as markdown skills; Python calls it via HTTP+SSE |
| **API** | FastAPI | Async, auto-Swagger, type-safe |
| **Storage** | SQLite + Parquet | Single file, zero infra for MVP |
| **Scheduler** | APScheduler | In-process cron, persistent jobs |
| **Indicators** | `pandas-ta-classic` | 252 indicators, no C deps |
| **Containerised** | Docker + Make | `make run` brings everything up |

**Phase 1 cost:** **₹0** (all free data sources, runs on laptop)
**Phase 2 (production):** ~₹500/mo (Fyers/Dhan paid data + EODHD fundamentals + PostgreSQL/TimescaleDB)

---

## 📊 Data Sources (after researching 25+ options)

**Free Phase 1 (swing mode, daily only):**
- **Market data:** `nselib` (daily, primary) + `yfinance` (fallback). No intraday provider needed.
- **Fundamentals:** Screener.in scraper (only free source with P/E + ROE + D/E + growth for NSE)
- **News:** Finnhub free tier + Moneycontrol/ET/Livemint RSS + NewsData.io

**Daily lifecycle (single pre-market run):**
```
22:00 IST (T-1)  ingest_fundamentals     (24h cached → no-op most days)
07:30 IST        ingest_ohlcv_daily      (append yesterday's candle only)
07:45 IST        ingest_news             (last 7 days, dedupe)
08:30 IST        run_analysis            (3 agents + aggregator → suggestions)
09:15 IST        ← market opens; you check /suggestions
```
Total: ~1 minute wall-time, ~80 external API calls per day.

**Why not Zerodha/others:** Zerodha Kite is ₹500/mo even on the cheapest tier; Alpha Vantage dropped Indian fundamentals; yfinance keeps getting rate-limited. The free Indian-native libs + RSS combo gives us all the data we need at zero cost.

---

## 🛣️ Roadmap (8 sprints, ~18 days)

```
Sprint 0  Bootstrap (Docker, FastAPI hello-world, Rovo CLI ping)         2d
Sprint 1  Data providers (market / fundamentals / news)                  3d
Sprint 2  Technical Analysis agent                                       2d
Sprint 3  Fundamental Analysis agent                                     2d
Sprint 4  News + sentiment agent                                         2d
Sprint 5  Aggregator + API endpoints                                     2d
Sprint 6  Scheduler + orchestrator polish                                2d
Sprint 7  Caching, retries, tests, README                                3d
```

**Phase 2 (later):** PostgreSQL, paid data, React UI, VectorBT backtesting.

---

## ✅ Why this design is solid

1. **Auditable** — every agent run persisted with `run_id`, inputs, score, reasoning. We can replay and backtest.
2. **Configurable** — weights, thresholds, watchlist all live in YAML (no code changes).
3. **Pluggable data** — swap free `nselib` for paid Fyers in Phase 2 by changing one config line.
4. **Resilient** — if one agent fails/times out, the other two still produce a partial suggestion.
5. **Reference pattern** — built on the same Rovo-Dev-CLI-only architecture as Atlassian's internal `disturbed-partner` repo (proven pattern, not invented from scratch).
6. **Disclaimer baked in** — every output carries *"Educational use only. Not financial advice."*

---

## 💡 Open questions

- Would a **daily digest** (email/Slack/Telegram) of top picks be useful?
- Phase 2 UI: simple **Streamlit** dashboard, or jump straight to a proper React frontend?
- Should we add a **Risk Agent** (volatility, beta, drawdown) as a 5th specialist?
- Phase 2: add **intraday** mode (1-hour candles) when we move to a paid broker API like Fyers / Dhan?

---

> **Disclaimer:** Educational and personal-research use only. Nothing here is financial, investment, or trading advice. Always consult a SEBI-registered advisor before making investment decisions.
