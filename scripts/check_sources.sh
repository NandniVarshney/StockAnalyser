#!/usr/bin/env bash
# Probe every data source one by one and print a coloured pass/fail summary.
# Requires FastAPI to be running (make api).
#
# Usage:
#   bash scripts/check_sources.sh
#   bash scripts/check_sources.sh http://localhost:8000     # override base URL
set -euo pipefail

BASE="${1:-http://localhost:8000}"
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'; BOLD='\033[1m'; NC='\033[0m'

echo ""
echo -e "${BOLD}━━━ StockAnalyser data-source health (${BASE}) ━━━${NC}"
echo ""

# 1) Liveness check — fail fast with a friendly message
if ! curl -s --max-time 3 "${BASE}/health" > /dev/null 2>&1; then
  echo -e "${RED}✗ FastAPI is NOT reachable at ${BASE}${NC}"
  echo ""
  echo "  Start it in another terminal:"
  echo "    make api"
  echo ""
  exit 1
fi

# 2) Probe — capture HTTP status + body separately
TMP_BODY="$(mktemp)"
trap 'rm -f "$TMP_BODY"' EXIT
HTTP_CODE="$(curl -s --max-time 60 -o "$TMP_BODY" -w '%{http_code}' "${BASE}/sources/health" || echo 000)"

if [ "$HTTP_CODE" != "200" ]; then
  echo -e "${RED}✗ ${BASE}/sources/health returned HTTP ${HTTP_CODE}${NC}"
  echo ""
  if [ "$HTTP_CODE" = "404" ]; then
    echo "  The /sources/health endpoint isn't registered on the running server."
    echo "  Restart FastAPI to pick up new routes:"
    echo "    (in the terminal running make api: Ctrl+C, then re-run)  make api"
  else
    echo "  Response body:"
    head -c 800 "$TMP_BODY" | sed 's/^/    /'
    echo ""
  fi
  exit 1
fi

# 3) Pretty-print using python3.
#    Pass the JSON via env var so stdin isn't shadowed by the heredoc.
JSON_BODY="$(cat "$TMP_BODY")" python3 <<'PY'
import json, os, sys
raw = os.environ.get("JSON_BODY", "")
if not raw:
    print("(empty response body)")
    sys.exit(1)
try:
    data = json.loads(raw)
except json.JSONDecodeError as e:
    print(f"Server returned non-JSON: {e}")
    print("First 400 chars of body:")
    print(raw[:400])
    sys.exit(1)

GREEN, RED, YELLOW, NC, BOLD = '\033[0;32m','\033[0;31m','\033[0;33m','\033[0m','\033[1m'

summary = data.get('summary', {})
print(f"{BOLD}Probe symbol{NC}: {data.get('probe_symbol','?')}")
print(f"{BOLD}Summary{NC}    : {GREEN}{summary.get('ok',0)} ok{NC} · "
      f"{RED}{summary.get('failed',0)} failed{NC} · "
      f"{YELLOW}{summary.get('skipped',0)} skipped{NC}\n")

print(f"{'NAME':<18}{'TYPE':<14}{'STATUS':<10}{'LATENCY':<10}{'NOTE'}")
print('-' * 110)
for s in data.get('sources', []):
    name = s.get('name', '?')
    typ  = s.get('type', '?')
    if s.get('skipped'):
        status = f"{YELLOW}skip{NC}    "
    elif s.get('ok'):
        status = f"{GREEN}OK{NC}      "
    else:
        status = f"{RED}FAIL{NC}    "
    lat = f"{s.get('latency_ms', '-')} ms" if s.get('latency_ms') is not None else '-'
    note = s.get('note') or s.get('error') or ''
    if isinstance(note, str) and len(note) > 70:
        note = note[:67] + '...'
    print(f"{name:<18}{typ:<14}{status:<19}{lat:<10}{note}")
print()
PY
