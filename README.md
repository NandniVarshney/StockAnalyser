# 📊 StockAnalyser

A multi-agent stock-suggestion app for **Indian NSE stocks** (swing-trading mode).
Three Rovo Dev agents analyse each stock — **Technical**, **Fundamental**, and **News** —
and a deterministic Python aggregator combines TA + FA into a single score with a
human-readable explanation. The news score is kept separate as a third independent signal.

> ⚠️ **Educational use only. Not financial advice.**

---

## ✨ What it does

```
22:00 IST (T-1)  ingest_fundamentals     (24h cached — usually no-op)
03:00 IST        cleanup_news            (drops news > 30 days old)
07:30 IST (T)    ingest_ohlcv_daily      (append yesterday's NSE candle only)
07:45 IST (T)    ingest_news             (Finnhub + 4 RSS feeds, dedupe by URL)
08:30 IST (T)    run_analysis            (3 agents + aggregator → suggestions)
09:15 IST        ← NSE opens; you check /suggestions
```

For every stock in your watchlist it produces a JSON like:
```json
{
  "stock": "RELIANCE",
  "combined_score": 35.2,
  "combined_signal": "SELL",
  "confidence": 0.45,
  "reasoning": "Combined score 35 → SELL. TA=25 (SELL). FA=42 (HOLD).",
  "news_score": 55.0,
  "news_signal": "HOLD",
  "news_reasoning": "Mixed: positive retail inflows offset by 'sharp declines' narrative."
}
```

---

## 🏗️ Architecture (one-screen view)

```
   external APIs ─▶ data providers ─▶ orchestrator ─▶ Rovo Dev CLI (:8766)
                                          │              ├ technical/SKILL.md
                                          │              ├ fundamental/SKILL.md
                                          │              └ news/SKILL.md
                                          │
                                          ▼
                                  deterministic
                                  aggregator (Python, no LLM)
                                          │
                                          ▼
                                   SQLite + Parquet
                                          │
                                          ▼
                                 FastAPI (:8000) ─▶ you
```

- **Push pattern**: orchestrator builds a self-contained payload (OHLCV + indicators +
  fundamentals + news) and sends it to the skill. Skills never read from storage.
- **Storage** is for audit + delta caching only.
- **Aggregator** is plain Python — same inputs always produce the same combined score.

See [`PLAN.md`](./PLAN.md) for the full design doc and [`OVERVIEW.md`](./OVERVIEW.md)
for a shareable summary.

---

## 🚀 Local setup

### 1. Prerequisites

| Tool | Why | How to install (macOS) |
|---|---|---|
| Python ≥ 3.11 | runtime | `brew install python@3.13` |
| `acli` (Atlassian CLI) | runs the local Rovo Dev server | per Atlassian internal docs |
| SQLite 3 | inspecting the DB | already on macOS |
| `make`, `bash`, `lsof`, `curl` | scripts | already on macOS |

### 2. Clone and bootstrap

```bash
cd ~/Desktop/code/StockAnalyser

# Creates .venv, installs all Python deps, copies .env.example → .env
make setup
```

### 3. Configure environment

```bash
cp .env.example .env   # done by make setup, but for reference
$EDITOR .env
```

| Variable | Default | Notes |
|---|---|---|
| `ROVODEV_SERVE_PORT` | `8766` | Local Rovo Dev CLI port |
| `APP_PORT` | `8000` | FastAPI port |
| `LOG_LEVEL` | `INFO` | `DEBUG` is much chattier |
| `AGGREGATOR_USE_LLM_REASONING` | `false` | Set true to use the optional polish skill |

### 4. Start the stack (two terminals)

**Terminal A — Rovo Dev CLI** (must come up first, takes ~30s to warm 22+ MCP servers)
```bash
make rovodev
# Wait for: "Rovo Dev CLI ready on :8766"
```

**Terminal B — FastAPI app**
```bash
make api
# → "Uvicorn running on http://0.0.0.0:8000"
```

### 5. Sanity-check

```bash
curl http://localhost:8000/health           # {"ok":true,...}
curl http://localhost:8000/rovodev/health   # {"ok":true,"rovodev_base_url":"http://localhost:8766"}
```

If both return `ok:true` you're good to go.

### 6. Try it

```bash
make analyze SYMBOL=RELIANCE
# … fetches data, runs 3 agents, prints final JSON.  Takes ~1-2 min the first time.
```

---

## 🛠️ Make targets

| Target | What it does |
|---|---|
| `make help` | List all targets with descriptions |
| `make setup` | Create `.venv`, install deps, copy `.env.example` → `.env` |
| `make rovodev` | Start `acli rovodev serve` on `:8766` |
| `make api` | Start FastAPI (uvicorn with reload) on `:8000` |
| `make run` | Start Rovo CLI **and** FastAPI together (single terminal) |
| `make health` | `curl /health` |
| `make ping` | `curl /rovodev/health` |
| `make analyze SYMBOL=XYZ` | Run the full pipeline for one stock via CLI (no API needed) |
| `make test` | Run `pytest` |
| `make lint` | Run `ruff check` |
| `make format` | Run `ruff format` |
| `make typecheck` | Run `mypy --strict` |
| `make clean` | Remove `.venv`, caches, logs |

---

## 🌐 REST API reference

All endpoints live on `http://localhost:8000`. Swagger UI is auto-generated at
**http://localhost:8000/docs**.

### Health

```bash
# Self
curl http://localhost:8000/health
# → {"ok":true,"service":"stockanalyser","version":"0.1.0"}

# Rovo CLI reachability
curl http://localhost:8000/rovodev/health
# → {"ok":true,"rovodev_base_url":"http://localhost:8766"}
```

### Watchlist

```bash
# List all tracked stocks (loaded from config/watchlist.yaml)
curl http://localhost:8000/watchlist | python3 -m json.tool
# →
# [
#   {"symbol":"RELIANCE","name":"Reliance Industries","sector":"Energy"},
#   {"symbol":"TCS","name":"Tata Consultancy Services","sector":"IT"},
#   ...
# ]

# Get one
curl http://localhost:8000/watchlist/RELIANCE

# Add a stock
curl -X POST http://localhost:8000/watchlist \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"BAJFINANCE","name":"Bajaj Finance","sector":"Financial Services"}'

# Remove a stock
curl -X DELETE http://localhost:8000/watchlist/BAJFINANCE
```

### Analyze (trigger a fresh run)

```bash
# Analyze one stock — synchronous, ~30-180 sec
curl -X POST http://localhost:8000/analyze/RELIANCE | python3 -m json.tool

# Analyze the full watchlist — ~15-30 min (serial because Rovo is single-session)
curl -X POST http://localhost:8000/analyze | python3 -m json.tool
```

Each call:
1. Loads OHLCV from cache (fetches only the delta since last run)
2. Loads fundamentals (24h cached) and recent news (last 7 days)
3. Pushes a self-contained payload into 3 Rovo agents (Technical → Fundamental → News)
4. Runs the deterministic aggregator
5. Persists `agent_runs` and `suggestions` rows
6. Returns the final JSON

### Suggestions (read latest results)

```bash
# All latest suggestions (one per stock)
curl http://localhost:8000/suggestions | python3 -m json.tool

# Just one stock's latest
curl http://localhost:8000/suggestions/RELIANCE | python3 -m json.tool

# Historical runs for one stock (audit trail)
curl http://localhost:8000/stock/RELIANCE/runs | python3 -m json.tool

# OHLCV slice (used by future UI)
curl "http://localhost:8000/stock/RELIANCE/ohlcv?days=60" | python3 -m json.tool
```

### Quick pretty-print one-liners

```bash
# Top picks by combined score
curl -s http://localhost:8000/suggestions | python3 -c "
import json, sys
rows = sorted(json.load(sys.stdin), key=lambda r: r['combined_score'], reverse=True)
for r in rows:
    print(f\"{r['symbol']:10} score={r['combined_score']:>5}  {r['combined_signal']:5}  conf={r['confidence']:.2f}\")"
```

---

## 🧠 The 4 agents

| Agent | Skill file | Input | Output |
|---|---|---|---|
| **Technical** | `.rovodev/subagents/technical/SKILL.md` | OHLCV daily + pre-computed indicators (RSI, MACD, Bollinger, SMA20/50/200, ATR, volume ratio) | `{score, signal, confidence, reasoning, signals_used}` |
| **Fundamental** | `.rovodev/subagents/fundamental/SKILL.md` | Latest P/E, ROE, ROCE, debt/equity, EPS, growth, sector medians | `{score, signal, confidence, reasoning, signals_used}` |
| **News** | `.rovodev/subagents/news/SKILL.md` | Last 7 days of news articles (deduped) | `{score, signal, confidence, reasoning, signals_used}` |
| **Aggregator** | `stockanalyser/aggregator.py` (pure Python) | TA + FA outputs | `combined_score = 0.4·TA + 0.6·FA`, threshold → BUY/HOLD/SELL |

**Weights & thresholds** are configurable in `config/weights.yaml`:
```yaml
weights:
  technical:   0.4
  fundamental: 0.6
thresholds:
  buy:  70    # >= 70 → BUY
  sell: 40    # <  40 → SELL ; 40..69 → HOLD
```

The aggregator is a deterministic Python function — same inputs always produce the same
score. Only the agents themselves involve an LLM.

---

## 📁 Project layout

```
StockAnalyser/
├── PLAN.md                       master design doc
├── OVERVIEW.md                   shareable pitch
├── README.md                     this file
├── LICENSE                       MIT
├── pyproject.toml                deps + ruff/mypy/pytest config
├── Makefile · run.sh             local launchers
├── Dockerfile · docker-compose.yml
│
├── .rovodev/subagents/           ← drop your strategies here
│   ├── technical/SKILL.md
│   ├── fundamental/SKILL.md
│   ├── news/SKILL.md
│   └── aggregator-reasoning/SKILL.md   (optional polish, off by default)
│
├── config/
│   ├── watchlist.yaml            15 Nifty stocks
│   ├── weights.yaml              0.4 TA + 0.6 FA, BUY≥70 / SELL<40
│   └── sources.yaml              provider routing + RSS feeds
│
├── stockanalyser/                Python package
│   ├── agents.py                 SkillKey enum + Pydantic schemas
│   ├── aggregator.py             deterministic Python
│   ├── rovo_client.py            HTTP+SSE → :8766/v2/chat
│   ├── config/                   pydantic-settings + YAML loaders
│   ├── utils/                    logging, time, http, hashing, ticker_map
│   ├── storage/                  SQLAlchemy models + Parquet store + repos
│   ├── providers/
│   │   ├── market/               nselib + yfinance + cache facade
│   │   ├── fundamentals/         screener + yfinance + cache facade
│   │   └── news/                 rss (Moneycontrol/ET/Livemint/BS) + dedupe facade
│   ├── orchestrator/             pipeline · indicators · sector_stats
│   ├── scheduler/                APScheduler jobs (cron in IST)
│   └── api/                      FastAPI routes
│
├── tests/                        pytest (smoke, aggregator, config)
├── data/ohlcv/                   Parquet OHLCV per symbol  (gitignored)
└── db/stockanalyser.db           SQLite                     (gitignored)
```

---

## 🗄️ Data persistence

### SQLite (`db/stockanalyser.db`)

| Table | Purpose |
|---|---|
| `watchlist` | Source of truth for tracked stocks (synced from YAML at boot) |
| `fundamentals_cache` | Latest Screener.in snapshot per symbol (24h TTL) |
| `news_articles` | Deduped by URL hash, 30-day retention |
| `agent_runs` | Every agent invocation: inputs hash, output JSON, latency, errors |
| `suggestions` | Final per-stock outputs from each pipeline run |

Inspect:
```bash
sqlite3 db/stockanalyser.db ".tables"
sqlite3 db/stockanalyser.db \
  "SELECT symbol, combined_score, combined_signal, confidence
   FROM suggestions ORDER BY as_of DESC LIMIT 10;" -header -column
```

Or use a GUI: `brew install --cask db-browser-for-sqlite && open db/stockanalyser.db`

### Parquet (`data/ohlcv/{SYMBOL}.parquet`)

Daily OHLCV per stock, append-only. 2-year cold-start backfill on first run.
Cache-first / fetch-delta strategy means we only call NSE for *new* candles.

---

## ⏰ Scheduled jobs

Auto-registered with APScheduler at FastAPI startup. All times **Asia/Kolkata**:

| Job | Cron | What it does |
|---|---|---|
| `ingest_fundamentals` | 22:00 daily | Refresh Screener (24h TTL → free no-op most days) |
| `cleanup_news` | 03:00 daily | Trim news > 30 days |
| `ingest_ohlcv_daily` | 07:30 daily | Append yesterday's candle (delta only) |
| `ingest_news` | 07:45 daily | Pull Finnhub + 4 RSS, dedupe by URL |
| `run_analysis` | 08:30 daily | TA + FA + NS + aggregator over the watchlist → `suggestions` ready before 09:15 |

Leave `make api` running and the daily run fires automatically.

---

## 🔍 Troubleshooting

### `make setup` → `python3.11: command not found`
The `Makefile` now auto-detects `python3.13` → `3.12` → `3.11`.
Install one: `brew install python@3.13` and re-run.

### `/rovodev/health` → `{"ok":false}`
Rovo Dev CLI isn't running. Start it in another terminal: `make rovodev`.
It takes ~30s to warm up. Verify with `curl http://localhost:8766/healthcheck`.

### `make analyze` → `409 Conflict` on Rovo calls
You're hitting two analyses simultaneously. Rovo CLI is single-session — wait for
the first to finish. The orchestrator already serialises the 3 agent calls within
one analysis.

### `Finnhub api key missing` warning
Phase 1 uses only RSS feeds for news (Finnhub free tier doesn't cover Indian stocks).
No API key needed.
RSS feeds give you Indian news without it.

### Screener.in scraper returns empty
Screener occasionally renames CSS classes. Check
`stockanalyser/providers/fundamentals/screener_provider.py::_parse_html` and
update the selectors against the live page.

### `nselib` rate limited / blocked
Sometimes NSE blocks data centre IPs. Workaround: run from your home IP or set
`MARKET_DATA_PRIMARY=yfinance` in `.env` to use the fallback.

### Resetting the DB / cache
```bash
rm -rf db/ data/ohlcv/
# Next analyze run will re-cold-start (2 years backfill).
```

---

## 🧪 Tests

```bash
make test                       # all pytest
.venv/bin/pytest -q -k aggreg   # one test
.venv/bin/pytest --tb=short     # short tracebacks
```

Tests are env-isolated (each gets a temp dir for SQLite + Parquet via `conftest.py`).
No network calls are made in unit tests.

---

## 📈 Roadmap

| Phase | Status | What |
|---|---|---|
| **Phase 1 (MVP, this repo)** | ✅ live | Swing mode, 15 stocks, free data, local SQLite + Parquet, 3 agents + aggregator, REST API, scheduler |
| Phase 2 | planned | Streamlit dashboard, paid data (Fyers/Dhan), PostgreSQL + TimescaleDB, Risk agent (5th specialist), email/Slack digest |
| Phase 3 | planned | Backtesting (VectorBT), paper-trading hook (Upstox sandbox), React UI |

---

## 🔗 Useful links

- Plan: [`PLAN.md`](./PLAN.md)
- Shareable overview: [`OVERVIEW.md`](./OVERVIEW.md)
- Swagger UI: http://localhost:8000/docs (when running)
- Rovo Dev CLI healthcheck: http://localhost:8766/healthcheck
- Rovo Dev CLI OpenAPI: http://localhost:8766/openapi.json
- Pattern reference: `atlassian/disturbed-partner` (rovo-dev-only-baseline)

---

## ⚠️ Disclaimer

This software is for **educational and research purposes only**. It is **not**
financial advice. Markets are risky; you can lose money. Any signals produced by
this app reflect the limitations of the data sources, the agent prompts, and the
weights you have configured. Always do your own research and consult a licensed
financial advisor before making investment decisions.
