# ─── StockAnalyser — developer Makefile ─────────────────────────────────────
# Mirrors the conventions from atlassian/disturbed-partner baseline.
# Phase-0 stubs; many targets become real once Sprint 0 scaffolding lands.
#
# Quick start:
#   make help          List all targets
#   make setup         One-time install of Python deps
#   make run           Start Rovo CLI + FastAPI (via run.sh)
#   make health        Ping both services
#   make test          Run pytest
# ────────────────────────────────────────────────────────────────────────────

SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

# Auto-detect a Python >=3.11. Override with `make PY=/path/to/python setup`.
PY        ?= $(shell command -v python3.13 || command -v python3.12 || command -v python3.11 || echo MISSING)
VENV      ?= .venv
PIP       := $(VENV)/bin/pip
PYTHON    := $(VENV)/bin/python
UVICORN   := $(VENV)/bin/uvicorn
RUFF      := $(VENV)/bin/ruff
MYPY      := $(VENV)/bin/mypy
PYTEST    := $(VENV)/bin/pytest

ROVODEV_SERVE_PORT ?= 8766
APP_PORT           ?= 8000

# ─── Help ───────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@echo ""
	@echo "StockAnalyser — available targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ─── Setup ──────────────────────────────────────────────────────────────────

.PHONY: setup
setup: $(VENV)/bin/activate ## One-time install of Python deps
	$(PIP) install -U pip wheel
	@if [ -f pyproject.toml ]; then $(PIP) install -e ".[dev]"; \
	elif [ -f requirements.txt ]; then $(PIP) install -r requirements.txt; \
	else echo "(no pyproject.toml / requirements.txt yet — add in Sprint 0)"; fi

$(VENV)/bin/activate:
	@if [ "$(PY)" = "MISSING" ]; then \
		echo ""; \
		echo "✗ No Python >=3.11 found on PATH."; \
		echo "  Install one of:"; \
		echo "    brew install python@3.13   (recommended)"; \
		echo "    brew install python@3.12"; \
		echo "    brew install python@3.11"; \
		echo "  Or run:  make PY=/path/to/python3 setup"; \
		echo ""; \
		exit 1; \
	fi
	@echo "[setup] Using Python: $(PY)"
	@$(PY) --version
	$(PY) -m venv $(VENV)

.PHONY: clean
clean: ## Remove venv, caches, build artefacts
	rm -rf $(VENV) .pytest_cache .ruff_cache .mypy_cache **/__pycache__ dist build *.egg-info

# ─── Run ────────────────────────────────────────────────────────────────────

.PHONY: rovodev
rovodev: ## Start `acli rovodev serve` only (stripped env, port 8766)
	bash run.sh rovodev

.PHONY: api
api: ## Start FastAPI only (uvicorn --reload)
	bash run.sh api

.PHONY: run
run: ## Start Rovo CLI + FastAPI together
	bash run.sh

.PHONY: health
health: ## Ping :8766/health and :8000/health
	bash run.sh health

# ─── Quality ────────────────────────────────────────────────────────────────

.PHONY: lint
lint: ## Ruff lint + format check
	$(RUFF) check stockanalyser tests
	$(RUFF) format --check stockanalyser tests

.PHONY: fmt
fmt: ## Ruff format (autofix)
	$(RUFF) format stockanalyser tests
	$(RUFF) check --fix stockanalyser tests

.PHONY: typecheck
typecheck: ## mypy --strict on stockanalyser/
	$(MYPY) --strict stockanalyser

.PHONY: test
test: ## Run pytest (unit + integration)
	$(PYTEST) -q

.PHONY: test-unit
test-unit: ## Run unit tests only
	$(PYTEST) -q tests/unit

# ─── App commands (post Sprint 0) ───────────────────────────────────────────

.PHONY: ping
ping: ## Sanity-check the Rovo CLI via our RovoClient
	$(PYTHON) -m stockanalyser ping

.PHONY: analyze
analyze: ## make analyze SYMBOL=RELIANCE
	$(PYTHON) -m stockanalyser analyze $(SYMBOL)

.PHONY: fetch
fetch: ## make fetch SYMBOL=RELIANCE — pull OHLCV + funda + news
	$(PYTHON) -m stockanalyser fetch $(SYMBOL)
