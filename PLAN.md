# StockAnalyser — Master Plan & Architecture

> **Repo target:** https://github.com/NandniVarshney/StockAnalyser
> **Owner:** Nandni Varshney
> **Status:** Phase 1 (MVP / Testing) — to be productionised later
> **Created:** 2026-05-26
> **Session:** w2454578-561d-417a-9e9a-c3369782ae50

This is the single source of truth for the **StockAnalyser** project. It captures every decision discussed plus the research-backed picks for data sources, frameworks, architecture, and execution roadmap. We will use this doc to drive implementation.

---

## 0. TL;DR (one screen)

- **What we're building:** A multi-agent Stock Suggestion App for **Indian (NSE) stocks**, **swing-trading mode only** (daily timeframe — no intraday). Four agents run per stock: **Technical Analysis (TA)**, **Fundamental Analysis (FA)**, **News/Sentiment (NS)**, and an **Aggregator** that combines TA+FA into a `combined_score` (with configurable weights) and keeps the news score `news_score` separate. Each agent returns a structured JSON with score, confidence, signal, and reasoning.
- **Scope:** Single-user (local, no auth, no multi-tenant). One curated watchlist of ~15 NSE stocks. One pre-market analysis run per day.
- **Agents engine:** **Rovo Dev only** — `acli rovodev serve` running locally on `:8766`; our Python orchestrator calls its `/v2/chat` SSE endpoint with structured inputs and a skill key. No LangChain / CrewAI / AutoGen. Pattern mirrors [`atlassian/disturbed-partner` (rovo-dev-only-baseline)](https://bitbucket.org/atlassian/disturbed-partner/src/rovo-dev-only-baseline/).
- **Phase 1 stock universe:** Curated watchlist of 10–20 NSE tickers (e.g., Nifty 50 subset) defined in `config/watchlist.yaml`. A future **Screener Agent** will eventually auto-pick stocks.
- **Phase 1 data stack (free, India-first):**
  - **Market data (OHLCV):** `nselib` (daily, primary) + `yfinance` (fallback). No intraday in Phase 1.
  - **Fundamentals:** Screener.in (via community wrapper / careful scrape) + `yfinance.info` for P/E sanity check
  - **News:** Finnhub free tier (60 req/min) + RSS feeds (Moneycontrol, Livemint, Economic Times, Business Standard) + NewsData.io as fallback
- **Phase 1 framework stack:** Python 3.11 + **FastAPI** (API) + **SQLite** (storage) + **APScheduler** (jobs) + **pandas-ta-classic** (indicators) + **pydantic-settings** (config) + **Docker Compose**
- **Phase 2 upgrades (when productionising):** Fyers / Dhan paid API for market data, EODHD for fundamentals, MarketAux/Alpha Vantage sentiment, PostgreSQL + TimescaleDB, Celery + Redis, Streamlit/Dash UI, VectorBT backtester, LangGraph if we outgrow simple orchestration.
- **Disclaimer baked into every output:** *Educational use only. Not financial advice.*

---

## 1. Goals & Non-Goals

### 1.1 Goals (Phase 1 MVP)
1. End-to-end pipeline: fetch → store → analyse (4 agents) → emit suggestion JSON.
2. Deterministic, auditable: every agent run is persisted with `run_id`, timestamp, inputs, score, reasoning.
3. India-first: NSE tickers, INR amounts, IST timestamps, Indian news sources.
4. Free / near-zero cost to run.
5. One developer can `docker compose up` and have it working locally.
6. Configurable weights & thresholds (no hard-coding).

### 1.2 Non-Goals (Phase 1)
- No real-money execution, no broker integration for orders.
- No frontend UI yet — JSON API + CLI is enough.
- No options / derivatives / portfolio optimisation.
- No backtesting *engine* (we'll log everything so we can backtest later).
- No multi-user auth / SaaS-grade hardening.

---

## 2. Data Source Decision (Research-Backed)

The deep research compared 12+ market-data sources, 10+ fundamentals sources, 13 news sources, and 8 framework categories. Below are the **final picks** with reasoning condensed.

### 2.1 Market Data (OHLCV) — Phase 1 Pick: `nselib (daily) + yfinance (fallback)`

Swing mode = daily candles only. Intraday providers are deferred to Phase 2.

| Source | Free? | Depth | Auth | MVP Verdict |
|---|---|---|---|---|
| **nselib** ✅ | Free | 5+ yrs daily | None | **Primary** |
| **yfinance** ⚠️ | Free | 20 yrs daily | None | **Fallback only** (rate-limit risky) |
| nsepython | Free | 365-day chunks, intraday too | None | Deferred — Phase 2 if we add intraday |
| nsetools | Free | Live quotes only | None | Not needed for swing |
| Upstox / Fyers / Dhan / Kite | mixed | full | OAuth | Phase 2 — paid/auth flows |
| Alpha Vantage / Tiingo / EODHD / Finnhub | mixed | limited India | API key | Phase 2 fallback |

**Why this pick for Phase 1**
- ₹0 cost, no broker account required, India-native.
- `nselib` v2.5.1 is actively maintained (2026) and gives us 5+ years of daily candles — more than enough for SMA200 + a year of backtest context.
- `yfinance` only invoked when `nselib` fails; uses caching + exponential backoff.
- Behind a `MarketDataProvider` abstraction so Phase 2 swap to Fyers/Dhan is a config change.

### 2.2 Fundamentals — Phase 1 Pick: `Screener.in (scraper) + yfinance.info (sanity)`

| Source | Free? | Covers P/E, ROE, D/E, EPS, Growth? | Verdict |
|---|---|---|---|
| **Screener.in** | Free (scrape) | ✅ All metrics | **Primary** — use community wrapper; cache aggressively; internal use only |
| yfinance `.info` | Free | Only P/E + market cap (financials broken for NSE) | Sanity check, secondary |
| Tickertape (unofficial) | Free | ✅ | Backup if Screener breaks |
| Alpha Vantage OVERVIEW | Free | ❌ NSE fundamentals removed Apr 2023 | Skip |
| Moneycontrol scrape | Free | ✅ | Redundant — skip |
| Tijori Finance | ₹330/mo, no API | ✅ | Skip (no API) |
| Trendlyne | No API | — | Skip |
| **EODHD fundamentals** | $59.99/mo | ✅ | **Phase 2 primary** |
| FMP | $99/mo | ⚠️ unclear NSE depth | Skip |

**Legal note:** Screener.in uses browsewrap ToS. Scraping publicly visible pages for internal analysis (no redistribution, no public API exposing their data) is the standard MVP pattern. We'll:
- Respect 1–2 req/sec with jitter.
- Cache for 24h (fundamentals change quarterly).
- Add `User-Agent` identifying the project + email.
- Add a Phase-2 migration switch to EODHD.

### 2.3 News & Sentiment — Phase 1 Pick: `Finnhub free + Indian RSS feeds + NewsData.io fallback`

| Source | Free tier | India coverage | Ticker mapping | Verdict |
|---|---|---|---|---|
| **Finnhub** | 60 req/min | ✅ supports `.NS` tickers | Direct | **Primary** |
| **RSS feeds** (Moneycontrol, Livemint, ET, Business Standard) | Unlimited | ✅✅✅ | Filter by company name | **Primary breadth** |
| **NewsData.io** | 200 credits/day | ✅ Indian publishers | Name-based, 12h delay | **Fallback / scale** |
| MarketAux | 100 req/day | ✅ `.BO` | Direct + built-in sentiment | Phase 2 |
| Alpha Vantage news | 25 req/day | medium | Direct + sentiment | Phase 2 |
| Tickertape news | Undocumented | ✅ | — | Risky — skip |
| Google News RSS | Free | medium | Manual query | ToS-risky |
| Twitter/X API | No free | — | — | Skip |
| Reddit (PRAW) | Limited | Low | Text search | Skip |

**Sentiment scoring:** Phase 1 uses **LLM-based scoring inside the Rovo Dev News Agent** — feed each article's title + summary; LLM returns `sentiment ∈ [-1, +1]` per article, agent aggregates. Phase 2 we'll either upgrade to Alpha Vantage premium sentiment or fine-tune **FinBERT** on Indian news.

**Daily load estimate (20 stocks):** ~20 Finnhub calls + 4 RSS pulls + ~20 NewsData calls = well within all free tiers.

### 2.4 Framework Stack — Phase 1

| Category | Pick | Why |
|---|---|---|
| Language | Python 3.11+ | Ecosystem fit |
| API | **FastAPI** | 5–10× faster than Flask, async, auto Swagger, type-safe |
| Storage | **SQLite** (single file) | Zero infra; sufficient for daily OHLCV + agent runs; trivial Docker mount |
| Time-series cache | **Parquet files** in `data/` | Cheap, fast for OHLCV |
| Scheduler | **APScheduler** with SQLAlchemyJobStore | In-process, persistent, Docker-friendly |
| Config | **pydantic-settings** + YAML for watchlist/weights | Type-safe, .env native |
| Technical indicators | **pandas-ta-classic** | Active 2026 fork, 252 indicators, no TA-Lib C dep |
| Agent orchestration | **Rovo Dev CLI (`acli rovodev serve`)** on `:8766` + Python orchestrator using `httpx` (SSE) + `asyncio.gather` | Rovo-Dev-only (no LangChain/CrewAI/AutoGen). Mirrors `disturbed-partner` baseline. Skills are markdown files in `.rovodev/subagents/<key>/SKILL.md`. |
| HTTP client | `httpx` (async) | Native async, plays well with FastAPI |
| Validation | `pydantic` v2 | Already pulled in by FastAPI |
| Logging | `structlog` (JSON logs) | Observability |
| Testing | `pytest` + `pytest-asyncio` + `respx` | Standard |
| Containerisation | **Docker + docker-compose** | One-command run |
| Linting | `ruff` + `black` + `mypy` | Modern, fast |
| Dependency mgmt | `uv` or `pip` + `requirements.txt` | Keep simple for MVP |

**Phase 2 upgrades:** PostgreSQL + TimescaleDB → Celery + Redis (broker) → Streamlit/Dash UI → VectorBT backtesting → LangGraph (if we outgrow plain async orchestration).

---

## 3. Architecture

### 3.1 High-Level System Flow (mirrors `disturbed-partner` baseline)

```
   ┌─────────────────────────────────────────────────────────────────────┐
   │  acli rovodev serve   (port 8766)   ← START FIRST in own terminal   │
   │  - 22+ MCP servers (Jira, Bitbucket, Confluence, K8s, ...)          │
   │  - HTTP endpoints: POST /v2/chat (SSE), GET /health                 │
   └────────────────────────────▲────────────────────────────────────────┘
                                │ HTTP POST + SSE stream
                                │
   ┌────────────────────────────┴────────────────────────────────────────┐
   │  StockAnalyser  (Python 3.11 / FastAPI :8000)                       │
   │                                                                     │
   │  ┌────────────────┐  ┌────────────────────┐  ┌──────────────────┐   │
   │  │  API layer     │  │   Orchestrator     │  │  RovoClient      │   │
   │  │  (FastAPI)     │─▶│   per-stock        │─▶│  httpx + SSE     │──▶ to :8766
   │  │  REST routes   │  │   asyncio.gather   │  │  parser, retries │   │
   │  └────────────────┘  └────────────────────┘  └──────────────────┘   │
   │           ▲                    │                                    │
   │           │                    ▼                                    │
   │  ┌────────┴───────┐  ┌────────────────────┐                         │
   │  │   APScheduler  │  │  Aggregator        │   DETERMINISTIC         │
   │  │  - 15m: prices │  │  (pure Python,     │   Python — no LLM       │
   │  │  - 60m: news   │  │   weighted sum +   │   (optional skill only  │
   │  │  - nightly: FA │  │   thresholds)      │    polishes reasoning)  │
   │  │  - 3×/d: run   │  └────────────────────┘                         │
   │  └────────────────┘                                                 │
   │                                                                     │
   │  ┌────────────────┐  ┌────────────────────┐                         │
   │  │  Providers     │  │  Storage           │                         │
   │  │  market/funda/ │  │  SQLite + Parquet  │                         │
   │  │  news (plug-   │  │  (agent_runs,      │                         │
   │  │  gable)        │  │   suggestions,...) │                         │
   │  └────────────────┘  └────────────────────┘                         │
   └─────────────────────────────────────────────────────────────────────┘
                                ▲
                                │
   ┌────────────────────────────┴────────────────────────────────────────┐
   │  External data sources                                              │
   │   nselib (daily) · yfinance (fallback) · Screener.in ·              │
   │   Finnhub · Moneycontrol/ET/Livemint/BS RSS · NewsData.io           │
   └─────────────────────────────────────────────────────────────────────┘

   Skills (markdown, version-controlled):
   .rovodev/subagents/
     ├── technical/SKILL.md          ← prompt + instructions for TA agent
     ├── fundamental/SKILL.md
     ├── news/SKILL.md
     └── aggregator-reasoning/SKILL.md  (optional, just for the prose summary)
```

### 3.2 Request Flow — `POST /analyze/{symbol}` (request / response, no SSE for Phase 1)

```
Client          FastAPI         Orchestrator        Providers        RovoClient      acli rovodev serve     SQLite
  │ POST /analyze  │                  │                  │                │                   │                │
  │ ─────────────▶ │ pipeline.run()   │                  │                │                   │                │
  │                │ ───────────────▶ │ fetch OHLCV   ─▶ │                │                   │                │
  │                │                  │ fetch funda   ─▶ │                │                   │                │
  │                │                  │ fetch news    ─▶ │                │                   │                │
  │                │                  │                  │                │                   │                │
  │                │                  │ asyncio.gather(  │                │                   │                │
  │                │                  │   invoke("technical",   inputs)  ─▶ POST /v2/chat ───▶│  SSE stream    │
  │                │                  │   invoke("fundamental", inputs)  ─▶ POST /v2/chat ───▶│  (accumulated, │
  │                │                  │   invoke("news",        inputs)  ─▶ POST /v2/chat ───▶│   final JSON   │
  │                │                  │   return_exceptions=True         │   parsed)          │                │
  │                │                  │ )                                │                                    │
  │                │                  │                                                                       │
  │                │                  │ deterministic_aggregator(TA, FA)  (Python — NO LLM call)              │
  │                │                  │   combined_score = w_ta*TA + w_fa*FA                                  │
  │                │                  │   signal = threshold(combined_score)                                  │
  │                │                  │                                                                       │
  │                │                  │ persist agent_runs[4] + suggestions[1] ──────────────────────────────▶│
  │                │ ◀─────────────── │ return Suggestion JSON                                                │
  │ ◀───────────── │                  │                                                                       │
```

**Phase 1 = synchronous request/response only.** SSE / live-stream surface is *not* exposed to clients in v0.1; we'll add a `GET /session/:id/stream` endpoint in Phase 2 when a React UI is on the roadmap.

### 3.3 Module Boundaries

```
stockanalyser/
├── api/              # FastAPI routes (thin)
├── orchestrator/     # Per-stock pipeline; asyncio.gather of agents
├── agents/           # Rovo Dev agent wrappers (Python adapters)
│   ├── technical.py
│   ├── fundamental.py
│   ├── news.py
│   └── aggregator.py
├── providers/        # Pluggable data sources
│   ├── market/       # nselib_provider, nsepython_provider, yfinance_provider
│   ├── fundamentals/ # screener_provider (only — sufficient for Indian stocks)
│   └── news/         # rss_provider (Moneycontrol/ET/Livemint/BS)
├── storage/          # SQLite models + parquet helpers
├── scheduler/        # APScheduler jobs
├── config/           # pydantic-settings + YAML loaders
└── utils/            # logging, caching, retries, ticker mapping
```

---

## 4. Agent Designs (Run by Rovo Dev)

Each agent is implemented as a **Rovo Dev agent / skill** with a strict JSON output contract. Our Python orchestrator only calls them and persists results.

### 4.0 Agent Invocation Contract (Rovo Dev CLI)

All three LLM agents (TA, FA, NS) are invoked via the **same** thin client. The aggregator is pure Python (no LLM).

**Endpoint:** `POST http://localhost:${ROVODEV_SERVE_PORT}/v2/chat`
(default port `8766`, matches `disturbed-partner`).

**Request payload (conceptual):**
```json
{
  "skill": "technical | fundamental | news",   // selects .rovodev/subagents/<key>/SKILL.md
  "inputs": {
    "symbol": "RELIANCE",
    "as_of": "2026-05-26T16:00:00+05:30",
    "ohlcv_daily":   [...],           // last 1-yr daily candles (TA only)
    "indicators":    {...},           // pre-computed RSI/MACD/etc (TA only)
    "fundamentals":  {...},           // dict of P/E, ROE, ... (FA only)
    "sector_medians":{...},           // computed from cohort (FA only)
    "news_articles": [...]            // last 7 days (NS only)
  },
  "context": { "run_id": "uuid", "parent_run_id": "uuid" }
}
```

**Response:** SSE stream. Our `RovoClient` accumulates `ANSWER_PART` tokens, parses the **last fenced JSON code block** of the final message, validates against the Pydantic schema below, and returns the dict. Trace events are logged but not surfaced to API clients in Phase 1.

**Timeouts (copied from `disturbed-partner` baseline):**
- `PER_AGENT_TIMEOUT_SEC=120` (2 min per agent call)
- `REQUEST_TIMEOUT_MS=180000` (3 min for the whole orchestrator call)

**Resilience:** `asyncio.gather(..., return_exceptions=True)` — if one agent fails or times out, the other two still run; aggregator handles partial results gracefully (drops the missing one and lowers confidence).

### 4.1 Shared Output Schema

```json
{
  "stock": "RELIANCE",
  "agent": "technical | fundamental | news | aggregator",
  "score": 0,                  // normalized 0-100
  "signal": "BUY | HOLD | SELL",
  "confidence": 0.0,           // 0-1
  "reasoning": "2-3 sentence human-readable explanation",
  "signals_used": ["RSI=62", "MACD bullish crossover"],
  "data_freshness": "2026-05-26T15:30:00+05:30",
  "run_id": "uuid",
  "timestamp": "ISO8601"
}
```

### 4.2 Agent 1 — Technical Analysis (TA)

- **Inputs:** Daily OHLCV (last 2 years — covers SMA200 + a year of context). **No intraday.**
- **Indicators (pandas-ta-classic):** RSI(14), MACD(12,26,9), Bollinger(20,2), SMA20, SMA50, SMA200, ATR(14), Daily volume vs 20-day average, recent support/resistance from daily closes.
- **Scoring rule (deterministic):** Each indicator contributes ±points; normalise to 0–100. *LLM only generates the reasoning string.* Keeps scores reproducible.
- **Confidence:** Higher when multiple indicators agree.

### 4.3 Agent 2 — Fundamental Analysis (FA)

- **Inputs:** P/E, P/B, ROE, ROCE, Debt/Equity, EPS, Revenue YoY, Profit YoY, Market Cap, Sector benchmarks (derived from watchlist cohort).
- **Scoring rule:** Z-score each metric vs sector median; weighted sum → 0–100.
- **Reasoning:** LLM explains "ROE 18% (sector median 12%) but D/E 1.4 elevated — net positive".

### 4.4 Agent 3 — News / Sentiment (NS) — kept separate

- **Inputs:** Last 7 days of news per ticker (Finnhub + RSS + NewsData merged, deduped by URL).
- **Process:** Rovo Dev LLM scores each article's sentiment ∈ [-1,+1]; agent weights by recency (decay over 7 days) and source quality; outputs `news_score` normalized to 0–100.
- **Output extras:** Top 3 catalysts (positive) + top 3 risks (negative) for the description.
- **Important:** NOT combined into `combined_score` — surfaced separately so user sees TA+FA vs news divergence.

### 4.5 Agent 4 — Aggregator (deterministic Python — no LLM)

Mirrors `disturbed-partner`'s "deterministic local synthesizer (no LLM)" pattern. Keeps Phase 1 cheap, fast, and reproducible.

- **Inputs:** TA + FA outputs (NS handled separately and reported alongside).
- **Formula (pure Python):**
  ```
  combined_score = w_ta * TA.score + w_fa * FA.score
  ```
  defaults: `w_ta=0.4, w_fa=0.6` (configurable via `config/weights.yaml`).
- **Thresholds (configurable):** `>=70 BUY`, `40–69 HOLD`, `<40 SELL`.
- **Confidence:** `min(TA.confidence, FA.confidence) * agreement_factor`.
- **Reasoning string:** Templated Python f-string by default (e.g. `"Above BUY threshold ({buy}). FA {fa_score} dominates TA {ta_score} at weights w_ta={w_ta}, w_fa={w_fa}."`).
- **Optional polish skill:** `.rovodev/subagents/aggregator-reasoning/SKILL.md` — invoked **only** for the human-readable summary string if `AGGREGATOR_USE_LLM_REASONING=true`. Score is always deterministic.

### 4.6 Final Suggestion Output

```json
{
  "stock": "RELIANCE",
  "as_of": "2026-05-26T16:00:00+05:30",
  "combined_score": 72,
  "combined_signal": "BUY",
  "confidence": 0.81,
  "reasoning": "Above BUY threshold (70). Strong ROE (18%) and earnings growth outweigh slightly overbought RSI.",
  "news_score": 55,
  "news_signal": "HOLD",
  "news_reasoning": "Mixed: positive Jio earnings offset by regulatory news on retail arm.",
  "agents": {
    "technical": { /* full TA agent output */ },
    "fundamental": { /* full FA agent output */ },
    "news": { /* full NS agent output */ }
  },
  "disclaimer": "Educational use only. Not financial advice."
}
```

---

## 5. Repository Layout

```
StockAnalyser/
├── README.md
├── PLAN.md                    # THIS FILE
├── LICENSE                    # MIT
├── .gitignore
├── .env.example
├── pyproject.toml             # or requirements.txt
├── ruff.toml
├── Dockerfile
├── docker-compose.yml
├── Makefile                   # make up | make test | make analyze
│
├── config/
│   ├── settings.py            # pydantic-settings BaseSettings
│   ├── watchlist.yaml         # 10–20 NSE tickers
│   ├── weights.yaml           # w_ta, w_fa, thresholds
│   └── sources.yaml           # which provider is primary per data type
│
├── .rovodev/
│   └── subagents/             # markdown skills, version-controlled
│       ├── technical/SKILL.md
│       ├── fundamental/SKILL.md
│       ├── news/SKILL.md
│       └── aggregator-reasoning/SKILL.md   # optional, only for prose
│
├── stockanalyser/
│   ├── __init__.py
│   ├── api/
│   │   ├── main.py            # FastAPI app
│   │   ├── routes_watchlist.py
│   │   ├── routes_analyze.py
│   │   └── routes_suggestions.py
│   ├── orchestrator/
│   │   ├── pipeline.py        # per-stock asyncio orchestration
│   │   └── runner.py          # batch runner used by scheduler
│   ├── rovo_client.py         # httpx + SSE client → :8766/v2/chat
│   ├── agents.py              # enum of skill keys + Pydantic output schemas
│   ├── aggregator.py          # deterministic Python aggregator (no LLM)
│   ├── providers/
│   │   ├── base.py            # abstract MarketData / Fundamentals / News
│   │   ├── market/
│   │   │   ├── nselib_provider.py        # primary (daily)
│   │   │   └── yfinance_provider.py      # fallback
│   │   ├── fundamentals/
│   │   │   ├── screener_provider.py
│   │   └── news/
│   │       ├── rss_provider.py
│   ├── storage/
│   │   ├── db.py              # SQLAlchemy engine
│   │   ├── models.py          # ORM tables
│   │   ├── repositories.py    # CRUD per entity
│   │   └── parquet_store.py   # OHLCV write/read helpers
│   ├── scheduler/
│   │   └── jobs.py            # APScheduler job definitions
│   ├── utils/
│   │   ├── ticker_map.py      # RELIANCE -> RELIANCE.NS / .BO / Finnhub
│   │   ├── http.py            # httpx client w/ retries + jitter
│   │   ├── cache.py           # disk/SQLite cache decorator
│   │   ├── logging.py         # structlog config
│   │   └── time.py            # IST helpers, market-hours checks
│   └── cli.py                 # `python -m stockanalyser analyze RELIANCE`
│
├── data/                      # gitignored (parquet OHLCV per stock)
├── db/                        # gitignored (sqlite files)
├── logs/                      # gitignored
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── notebooks/                 # exploration only
```

---

## 6. Data Model (SQLite via SQLAlchemy)

```sql
-- Curated watchlist
CREATE TABLE watchlist (
  symbol        TEXT PRIMARY KEY,        -- 'RELIANCE'
  company_name  TEXT NOT NULL,
  sector        TEXT,
  added_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
  active        BOOLEAN DEFAULT 1
);

-- Latest fundamentals snapshot (refreshed nightly)
CREATE TABLE fundamentals_cache (
  symbol        TEXT NOT NULL,
  fetched_at    DATETIME NOT NULL,
  source        TEXT NOT NULL,           -- 'screener' | 'yfinance' | 'eodhd'
  pe REAL, pb REAL, roe REAL, roce REAL,
  debt_equity REAL, eps REAL, market_cap REAL,
  revenue_yoy REAL, profit_yoy REAL,
  raw_json      TEXT,                    -- full payload for audit
  PRIMARY KEY(symbol, fetched_at)
);

-- News articles cache
CREATE TABLE news_articles (
  id            TEXT PRIMARY KEY,        -- hash of url
  symbol        TEXT NOT NULL,
  source        TEXT NOT NULL,           -- 'moneycontrol' | 'economic_times' | 'livemint' | 'business_std'
  title         TEXT NOT NULL,
  url           TEXT NOT NULL,
  summary       TEXT,
  published_at  DATETIME NOT NULL,
  fetched_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- One row per agent execution (full audit trail)
CREATE TABLE agent_runs (
  run_id        TEXT PRIMARY KEY,
  parent_run_id TEXT,                    -- groups TA/FA/NS/Agg for same analyze() call
  symbol        TEXT NOT NULL,
  agent         TEXT NOT NULL,           -- technical | fundamental | news | aggregator
  score         REAL,
  signal        TEXT,
  confidence    REAL,
  reasoning     TEXT,
  signals_used  TEXT,                    -- JSON array
  inputs_hash   TEXT,                    -- hash of inputs for cache/dedup
  raw_output    TEXT,                    -- full JSON from Rovo Dev
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Final suggestion (1 per stock per analyse run)
CREATE TABLE suggestions (
  parent_run_id  TEXT PRIMARY KEY,
  symbol         TEXT NOT NULL,
  as_of          DATETIME NOT NULL,
  combined_score REAL, combined_signal TEXT, confidence REAL, reasoning TEXT,
  news_score     REAL, news_signal TEXT, news_reasoning TEXT,
  weights_json   TEXT,                   -- captures w_ta, w_fa used
  thresholds_json TEXT
);

CREATE INDEX idx_runs_symbol_time ON agent_runs(symbol, created_at DESC);
CREATE INDEX idx_news_symbol_time ON news_articles(symbol, published_at DESC);
CREATE INDEX idx_sugg_symbol_time ON suggestions(symbol, as_of DESC);
```

**OHLCV** lives in **Parquet** files (`data/ohlcv/{symbol}.parquet`) — cheaper for time-series than SQLite, easy to read with pandas. **Daily candles only** in Phase 1 — no separate intraday store.

### 6.1 Cache Strategy (read-first / fetch-delta)

Providers always read cache first, fetch only the missing delta, write back. Skills never read storage — they get fully-built payloads from the orchestrator (push pattern). This keeps the daily run to **~80 external calls instead of ~2000**.

| Data | Where it lives | Read pattern | Write pattern | TTL |
|---|---|---|---|---|
| Daily OHLCV | `data/ohlcv/{symbol}.parquet` | read parquet first | append candles since `last_date+1` | none — incremental |
| Fundamentals | `fundamentals_cache` table | use latest row if `<24h` old | upsert full row | 24h |
| News articles | `news_articles` table | always fetch fresh window | `INSERT OR IGNORE` on URL hash (dedupe) | 30-day retention |
| Indicators (RSI/MACD/…) | computed at orchestrator | recompute every run from OHLCV | not persisted | — |
| Sector medians | computed at orchestrator from cohort | recompute every run | not persisted | — |
| Agent JSON outputs | `agent_runs` table | not read by skills (audit only) | persist every run | — |

**Cold start (first ever run):** backfill `ohlcv_backfill_years=2` of daily history per stock (~500 candles × 15 stocks ≈ one minute). After that, every daily run fetches **just yesterday's candle** per stock.

---

## 7. Configuration (pydantic-settings + YAML)

`config/settings.py`:
```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Secrets / API keys
    # Phase 1 has no required API keys — all sources are free + key-less.

    # Storage
    sqlite_path: str = "db/stockanalyser.db"
    parquet_dir: str = "data/ohlcv"

    # Behaviour (swing mode — daily only)
    timezone: str = "Asia/Kolkata"
    fundamentals_ttl_hours: int = 24
    ohlcv_backfill_years: int = 2
    news_retention_days: int = 30

    # Rovo Dev CLI (matches disturbed-partner baseline)
    rovodev_serve_port: int = 8766
    rovodev_base_url: str = "http://localhost:8766"
    rovodev_binary_path: str | None = None          # auto-detect `acli`
    rovodev_working_dir: str | None = None          # defaults to cwd
    request_timeout_ms: int = 180_000               # 3 min orchestrator-wide
    per_agent_timeout_sec: int = 120                # 2 min per agent
    aggregator_use_llm_reasoning: bool = False      # keep aggregator deterministic in Phase 1

    # Atlassian context (read by `acli rovodev serve`)
    atlassian_site: str | None = None
    atlassian_cloud_id: str | None = None
    atlassian_api_token: str | None = None
    atlassian_account_id: str | None = None
```

`config/weights.yaml`:
```yaml
weights:
  technical: 0.4
  fundamental: 0.6
thresholds:
  buy:  70
  sell: 40
news_thresholds:
  positive: 60
  negative: 40
```

`config/watchlist.yaml` (starter Nifty subset):
```yaml
stocks:
  - {symbol: RELIANCE,  name: "Reliance Industries",   sector: Energy}
  - {symbol: TCS,       name: "Tata Consultancy",      sector: IT}
  - {symbol: INFY,      name: "Infosys",               sector: IT}
  - {symbol: HDFCBANK,  name: "HDFC Bank",             sector: Banking}
  - {symbol: ICICIBANK, name: "ICICI Bank",            sector: Banking}
  - {symbol: ITC,       name: "ITC",                   sector: FMCG}
  - {symbol: LT,        name: "Larsen & Toubro",       sector: Infra}
  - {symbol: SBIN,      name: "State Bank of India",   sector: Banking}
  - {symbol: BHARTIARTL,name: "Bharti Airtel",         sector: Telecom}
  - {symbol: HINDUNILVR,name: "Hindustan Unilever",    sector: FMCG}
  - {symbol: AXISBANK,  name: "Axis Bank",             sector: Banking}
  - {symbol: KOTAKBANK, name: "Kotak Mahindra Bank",   sector: Banking}
  - {symbol: MARUTI,    name: "Maruti Suzuki",         sector: Auto}
  - {symbol: ASIANPAINT,name: "Asian Paints",          sector: Materials}
  - {symbol: SUNPHARMA, name: "Sun Pharma",            sector: Pharma}
```

`config/sources.yaml`:
```yaml
market_data:
  primary: nselib       # daily only (swing mode)
  fallback: yfinance
fundamentals:
  primary: screener
  sanity: yfinance
news:
  primary: [rss]
```

---

## 8. API Endpoints (FastAPI)

| Method | Path                          | Purpose |
|---|---|---|
| GET    | `/health`                     | Liveness |
| GET    | `/watchlist`                  | Current tracked stocks |
| POST   | `/watchlist`                  | Add stock |
| DELETE | `/watchlist/{symbol}`         | Remove stock |
| POST   | `/analyze`                    | Trigger analysis (sync) for full watchlist or a list |
| POST   | `/analyze/{symbol}`           | Analyse one ticker |
| GET    | `/suggestions`                | Latest suggestion per stock (with filters: date, signal) |
| GET    | `/suggestions/{symbol}`       | Historical suggestions for one stock |
| GET    | `/stock/{symbol}/runs`        | Raw agent runs (debug / audit) |
| GET    | `/stock/{symbol}/ohlcv`       | OHLCV slice (used by future UI) |
| GET    | `/rovodev/health`             | Proxies `http://localhost:8766/health` so users can verify the CLI is up |

**Phase 1 = synchronous JSON only.** No SSE / streaming surface yet. The `RovoClient` consumes SSE *internally* from the CLI but our FastAPI returns the final JSON only.

**Phase 2 additions** (mirroring `disturbed-partner` baseline if/when we add a UI):
- `POST /session/message`, `POST /session/:id/message`
- `GET  /session/:id/state`
- `GET  /session/:id/stream`   (SSE for live trace events)
- `POST /session/:id/answer-now`, `DELETE /session/:id`

Swagger UI available automatically at `/docs`.

---

## 9. Scheduling Plan (APScheduler with SQLAlchemyJobStore)

**Swing mode = one analysis run per day, before market opens.** The whole daily lifecycle is ~1 minute of wall-time and well under 100 external API calls.

| Job | Cron (IST) | What it does |
|---|---|---|
| `ingest_fundamentals`   | 22:00 daily (T-1) | Refresh Screener.in for watchlist (24h TTL → free no-op most days) |
| `cleanup_news`          | 03:00 daily | Trim news older than `news_retention_days` (default 30) |
| `ingest_ohlcv_daily`    | 07:30 daily | Append yesterday's daily candle (cache delta, see §6.1) |
| `ingest_news`           | 07:45 daily | Pull Finnhub + RSS, dedupe by URL hash |
| `run_analysis`          | 08:30 daily | Run TA + FA + NS agents in parallel + aggregator; write `suggestions` (ready before 09:15 market open) |

**No intraday jobs.** No market-hours gating needed. Weekends/holidays: jobs still run but most will be no-ops (no new candle, no funda change).

---

## 10. Execution Roadmap (Milestones)

### Sprint 0 — Bootstrap (Day 1–2)
1. Create GitHub repo `NandniVarshney/StockAnalyser`, clone locally to `~/Desktop/code/StockAnalyser`.
2. Add `README.md`, `LICENSE` (MIT), `.gitignore`, `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `Makefile`, `run.sh`.
3. Scaffold directory tree from §5 (including `.rovodev/subagents/`).
4. Wire `pydantic-settings`, `.env.example`, structlog, FastAPI hello-world.
5. **Verify Rovo Dev CLI is reachable** before any agent code:
   ```bash
   # Terminal A — start CLI (stripped env to avoid leaking your shell config; copied from disturbed-partner)
   env -i HOME=$HOME PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
     USER=$USER SHELL=$SHELL TERM=xterm-256color \
     acli rovodev serve 8766 --disable-session-token

   # Terminal B — wait for ready, then ping
   curl http://localhost:8766/health
   ```
6. Implement minimal `RovoClient` that POSTs a "hello" prompt and returns the assistant text.
- **Exit criteria:** `make run` starts the FastAPI app on `:8000`; `GET /health` → `{"ok": true}`; `GET /rovodev/health` → CLI reachable; `python -m stockanalyser ping` returns a Rovo-generated greeting.

### Sprint 1 — Data Providers (Day 3–5)
- Implement `MarketDataProvider` abstract + `nselib_provider`, `nsepython_provider`, `yfinance_provider` (fallback).
- Implement `FundamentalsProvider` + `screener_provider`.
- Implement `NewsProvider` + `rss_provider` (Moneycontrol / ET / Livemint / BS).
- Persist OHLCV → Parquet; fundamentals + news → SQLite.
- Unit tests with `respx` mocks; integration test fetching `RELIANCE`.
- **Exit criteria:** `python -m stockanalyser fetch RELIANCE` populates DB + parquet.

### Sprint 2 — Technical Agent (Day 6–7)
- Wrap Rovo Dev call: pass last 1-yr daily OHLCV + 30-day intraday + computed indicators (RSI/MACD/Bollinger/SMA50/200/ATR via pandas-ta-classic).
- Deterministic score; LLM only for `reasoning`.
- Persist `agent_runs` row.

### Sprint 3 — Fundamental Agent (Day 8–9)
- Compute sector medians from watchlist; z-score each metric.
- Rovo Dev produces reasoning string with sector benchmark commentary.

### Sprint 4 — News Agent (Day 10–11)
- Merge + dedupe Finnhub + RSS + NewsData articles for last 7 days.
- Rovo Dev scores each article; agent aggregates with recency decay.
- Output kept separate from combined score.

### Sprint 5 — Aggregator + API (Day 12–13)
- Implement aggregator (configurable weights).
- Wire `POST /analyze`, `GET /suggestions` etc.
- Persist `suggestions` table.

### Sprint 6 — Scheduler + Orchestrator polish (Day 14–15)
- APScheduler jobs from §9.
- `asyncio.gather` orchestrator with timeouts + per-agent error isolation.
- Structured JSON logs; `run_id` tracing.

### Sprint 7 — Hardening (Day 16–18)
- Caching (cache fundamentals 24h, news 1h).
- Exponential backoff for yfinance / Screener.
- Pytest coverage > 70% for core modules.
- README walkthrough + screenshots.

### Sprint 8 — Phase-2 prep (optional)
- Add `Fyers`/`Dhan` providers behind same abstraction.
- Migration script SQLite → Postgres+TimescaleDB.
- Streamlit dashboard PoC.
- VectorBT backtest harness using stored agent runs.

---

## 11. Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| `nselib`/`nsepython` breaks when NSE changes site | Med | Keep version pin loose; alert on consecutive failures; fallback to yfinance + log a ticket |
| `yfinance` rate-limit / IP block | High when bursty | Cache aggressively; jittered backoff; not the primary source |
| Screener.in ToS / blocking | Med | 1–2 req/sec, identifying UA, internal-only use, plan EODHD migration |
| Finnhub India coverage gaps | Med | RSS feeds compensate; News agent merges multi-source |
| Rovo Dev rate limits / token cost | Med | Per-agent caching keyed on `inputs_hash`; only re-run when inputs change |
| Local Rovo CLI process dies / unreachable on `:8766` | Med | `RovoClient` does fail-fast with circuit breaker; orchestrator returns 503 from `/analyze` and surfaces a "CLI unavailable" message; APScheduler skips this tick |
| Single Rovo agent timeout (>2 min) kills the whole analysis | Low | `asyncio.gather(..., return_exceptions=True)` — partial results allowed; aggregator reports lower confidence and notes missing agent |
| SSE parsing drift if CLI changes its event format | Low–Med | Keep `RovoClient` parser tolerant; pin a known-good `acli` version in `.tool-versions`; integration test fixtures captured from real CLI |
| Bad signals → user trusts them | High (UX) | Embed disclaimer in every output; surface confidence + divergence between TA+FA and news |
| Time drift / IST handling | Low | Use `zoneinfo.ZoneInfo("Asia/Kolkata")` everywhere |
| Quarterly earnings staleness | Med | Re-fetch fundamentals nightly; flag `data_freshness` per agent |
| Cloud deployment blocked by NSE | Low (local now) | Server-mode of `nsepython` is firewalled outside India — keep local for Phase 1, broker API for cloud Phase 2 |

---

## 12. Tooling Conventions

- **Style:** `ruff` (lint+format) + `mypy --strict` on `stockanalyser/`.
- **Commits:** Conventional Commits (`feat:`, `fix:`, `chore:`).
- **Branches:** `main` (protected) + short-lived feature branches; PRs required.
- **CI:** GitHub Actions — lint + tests on every PR (set up in Sprint 1).
- **Versioning:** SemVer; tag `v0.1.0` after Sprint 5.
- **Secrets:** `.env` (gitignored); CI uses GH Secrets.

---

## 13. Open Questions for Next Iteration

1. ~~**Rovo Dev invocation**~~ — **RESOLVED:** HTTP+SSE on `http://localhost:8766/v2/chat`, skills authored as markdown in `.rovodev/subagents/<key>/SKILL.md`. Phase 1 = synchronous request/response from FastAPI; no SSE surface to clients yet.
2. **Stock universe Phase 2:** Stay manual or build Screener Agent that picks based on volume + market cap?
3. **Hosting Phase 2:** Local-only? AWS Lightsail in `ap-south-1` (Mumbai) to keep NSE-Python-friendly IP?
4. **Notification channel:** Email digest? Slack? Telegram?
5. **Paper trading hook (Phase 3):** Should suggestions auto-place paper trades via Upstox/Fyers sandbox for KPI tracking?
6. **Web UI (Phase 2):** Will we mirror `disturbed-partner`'s React frontend + SSE session stream? If yes, retrofit the gateway-style session endpoints listed in §8.

---

## 14. References (Selected)

**Market data**
- `nselib` — https://pypi.org/project/nselib/
- `nsepython` — https://unofficed.com/nse-python/
- Fyers free API — https://fyers.in/
- Dhan Data API — https://dhan.co/dropdown/data-apis
- Zerodha Kite Connect — https://kite.trade/

**Fundamentals**
- Screener.in — https://www.screener.in/
- EODHD — https://eodhd.com/
- Tijori Finance — https://www.tijorifinance.com/

**News**
- Moneycontrol RSS — https://www.moneycontrol.com/rss/
- Economic Times RSS — https://economictimes.indiatimes.com/rss.cms
- MarketAux — https://www.marketaux.com/

**Frameworks**
- FastAPI — https://fastapi.tiangolo.com/
- pandas-ta-classic — https://pypi.org/project/pandas-ta-classic/
- APScheduler — https://apscheduler.readthedocs.io/
- pydantic-settings — https://docs.pydantic.dev/latest/concepts/pydantic_settings/
- VectorBT (Phase 2) — https://vectorbt.dev/
- Streamlit (Phase 2) — https://streamlit.io/

---

## 15. Reference Implementation

We are deliberately mirroring the **Rovo-Dev-CLI-only** pattern from:

**Repo:** [`atlassian/disturbed-partner`](https://bitbucket.org/atlassian/disturbed-partner/src/rovo-dev-only-baseline/) — branch `rovo-dev-only-baseline`

**Files worth studying / copying patterns from:**
- `README.md` — full setup walkthrough including the `env -i … acli rovodev serve 8766` launch incantation, port assignments, and health-check sequence.
- `run.sh` — multi-process launcher with `kill_port`, `wait_for_health`, and trap-based cleanup. We'll port this to bash for our 2-process setup (CLI + FastAPI).
- `gateway/.env.example` — canonical env-var names (`ATLASSIAN_SITE`, `ATLASSIAN_CLOUD_ID`, `ATLASSIAN_API_TOKEN`, `ATLASSIAN_ACCOUNT_ID`, `ROVODEV_SERVE_PORT`, `REQUEST_TIMEOUT_MS`, `SESSION_TTL_MS`).
- `gateway/src/` — the SSE client + session orchestration model (TypeScript) to translate into Python's `httpx` + `asyncio`.
- `gateway/skills/` — markdown skills with YAML frontmatter (`key`, `name`, `match_patterns`); drop-a-markdown-file → new agent. Same pattern in our `.rovodev/subagents/`.

**Differences from the baseline (intentional):**
- Python (not Node/TypeScript) — chosen for India-data + ML ecosystem (see Python vs Node analysis discussed earlier).
- Single-track per stock instead of two parallel investigation tracks; our four agents are *different roles*, not redundant analysers.
- Aggregator stays deterministic (no LLM) — same philosophy as their `synthesizeLocally` for OpsGenie alerts.
- No Slack bot or React UI in Phase 1 — purely a backend service; can be added later if useful.

---

## 16. Disclaimer

This project is for **educational and personal research purposes only**. Nothing produced by StockAnalyser constitutes financial, investment, trading, or other professional advice. Always consult a SEBI-registered advisor before making investment decisions. The authors accept no liability for any decisions made using this tool.

<!-- session_id: w2454578-561d-417a-9e9a-c3369782ae50 -->



