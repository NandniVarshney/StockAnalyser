#!/usr/bin/env bash
# ─── StockAnalyser — local dev launcher ──────────────────────────────────────
# Mirrors the pattern from atlassian/disturbed-partner (rovo-dev-only-baseline)
# Adapted for Python / FastAPI + acli rovodev serve.
#
# Usage:
#   bash run.sh              Start everything (waits for Rovo CLI, then FastAPI)
#   bash run.sh api          Start FastAPI only (assumes Rovo CLI already running)
#   bash run.sh rovodev      Start `acli rovodev serve` only (foreground)
#   bash run.sh health       Ping :8766 and :8000 health endpoints
#
# Required env (loaded from .env if present):
#   ROVODEV_SERVE_PORT=8766
#   APP_PORT=8000
#   ATLASSIAN_SITE, ATLASSIAN_CLOUD_ID, ATLASSIAN_API_TOKEN, ATLASSIAN_ACCOUNT_ID
#
# Ctrl+C shuts down all child processes.
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PIDS=()

# Load .env if present
if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.env"
  set +a
fi

ROVODEV_SERVE_PORT="${ROVODEV_SERVE_PORT:-8766}"
APP_PORT="${APP_PORT:-8000}"

# Prefer the project's virtualenv if it exists. This means `make api` /
# `bash run.sh api` Just Works without the user having to `source .venv/bin/activate`.
if [ -z "${VIRTUAL_ENV:-}" ] && [ -x "$SCRIPT_DIR/.venv/bin/uvicorn" ]; then
  # Prepend venv bin so `uvicorn`, `python`, etc. resolve there.
  export PATH="$SCRIPT_DIR/.venv/bin:$PATH"
  export VIRTUAL_ENV="$SCRIPT_DIR/.venv"
fi

cleanup() {
  echo ""
  echo "[run] Shutting down..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  pkill -P $$ 2>/dev/null || true
  wait 2>/dev/null || true
  echo "[run] All services stopped."
}
trap cleanup EXIT INT TERM

kill_port() {
  local port=$1
  local pids
  pids=$(lsof -ti:"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "[run] Killing existing process on port $port"
    echo "$pids" | xargs kill -9 2>/dev/null || true
    sleep 1
  fi
}

wait_for_health() {
  local url=$1
  local max_wait=$2
  local label=$3
  local elapsed=0
  echo "[run] Waiting for $label at $url ..."
  while [ "$elapsed" -lt "$max_wait" ]; do
    if curl -sf "$url" >/dev/null 2>&1; then
      echo "[run] ✓ $label healthy"
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  echo "[run] ✗ $label failed to start within ${max_wait}s"
  return 1
}

start_rovodev() {
  kill_port "$ROVODEV_SERVE_PORT"
  echo "[run] Starting acli rovodev serve on :$ROVODEV_SERVE_PORT ..."
  # Stripped-env launch — copied verbatim from disturbed-partner README.
  # Prevents your shell's leaked env vars from confusing the CLI.
  env -i HOME="$HOME" \
        PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
        USER="$USER" SHELL="$SHELL" TERM="${TERM:-xterm-256color}" \
    acli rovodev serve "$ROVODEV_SERVE_PORT" --disable-session-token &
  PIDS+=($!)
}

start_api() {
  kill_port "$APP_PORT"
  cd "$SCRIPT_DIR"

  # Prefer venv's uvicorn; fall back to `python -m uvicorn` (still uses venv);
  # finally bail with a clear message if nothing is installed.
  if [ -x "$SCRIPT_DIR/.venv/bin/uvicorn" ]; then
    UVICORN_CMD=("$SCRIPT_DIR/.venv/bin/uvicorn")
  elif [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    UVICORN_CMD=("$SCRIPT_DIR/.venv/bin/python" -m uvicorn)
  elif command -v uvicorn >/dev/null 2>&1; then
    UVICORN_CMD=(uvicorn)
  else
    echo "[run] ✗ uvicorn not found."
    echo "      Run \`make setup\` first to create .venv and install deps."
    exit 1
  fi

  echo "[run] Starting FastAPI on :$APP_PORT  (${UVICORN_CMD[*]})"
  "${UVICORN_CMD[@]}" stockanalyser.api.main:app --host 0.0.0.0 --port "$APP_PORT" --reload &
  PIDS+=($!)
}

health() {
  echo "[run] Rovo CLI  ($ROVODEV_SERVE_PORT): $(curl -sf "http://localhost:$ROVODEV_SERVE_PORT/health" || echo 'DOWN')"
  echo "[run] FastAPI   ($APP_PORT): $(curl -sf "http://localhost:$APP_PORT/health" || echo 'DOWN')"
}

# ─── Main ────────────────────────────────────────────────────────────────────

case "${1:-}" in
  rovodev)
    start_rovodev
    wait
    ;;
  api)
    start_api
    wait
    ;;
  health)
    health
    ;;
  "")
    # Full stack: Rovo CLI first, then FastAPI
    start_rovodev
    wait_for_health "http://localhost:$ROVODEV_SERVE_PORT/health" 60 "Rovo CLI"
    start_api
    wait_for_health "http://localhost:$APP_PORT/health" 20 "FastAPI"

    echo ""
    echo "─── All services running ───────────────────────────────────"
    echo "  Rovo CLI:    http://localhost:$ROVODEV_SERVE_PORT"
    echo "  FastAPI:     http://localhost:$APP_PORT"
    echo "  Swagger UI:  http://localhost:$APP_PORT/docs"
    echo "  Press Ctrl+C to stop all"
    echo "────────────────────────────────────────────────────────────"
    echo ""

    wait
    ;;
  *)
    echo "[run] Unknown: $1. Use: rovodev | api | health | (empty for all)"
    exit 1
    ;;
esac
