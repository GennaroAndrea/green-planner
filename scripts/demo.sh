#!/usr/bin/env bash
# Demo launcher (plan §8, item 4.1): data → frontend build → uvicorn on :8080 → ngrok.
#
#   scripts/demo.sh            full demo, public URL via ngrok
#   scripts/demo.sh --local    same app on http://localhost:8080, no ngrok
#
# Data: data/processed/ if built; otherwise it is rebuilt offline from data/raw/;
# otherwise the committed snapshot in deploy/data/ is used (see deploy/README.md).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="$HOME/.local/bin:$PATH"

PORT="${DEMO_PORT:-8080}"
NGROK_URL="${DEMO_NGROK_URL:-https://green-planner.ngrok.io}"
LOG="$ROOT/data/interim/demo_uvicorn.log"
LOCAL=0
[[ "${1:-}" == "--local" ]] && LOCAL=1

step() { printf '\n\033[1;32m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

command -v uv >/dev/null || fail "uv not found (expected in ~/.local/bin)"
command -v npm >/dev/null || fail "npm not found"
if ((LOCAL == 0)); then command -v ngrok >/dev/null || fail "ngrok not found (or use --local)"; fi
if (echo >"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
  fail "port $PORT is already in use (another demo running?)"
fi

step "Python environment"
uv sync --frozen --quiet

step "Data"
DATA_DIR="$ROOT/data/processed"
if [[ -f "$DATA_DIR/metadata.json" ]]; then
  echo "using data/processed/"
elif compgen -G "data/raw/sentinel2_ndvi/*" >/dev/null; then
  echo "data/processed/ is empty: rebuilding it from data/raw/ (offline, about 30 s)"
  uv run python -m pipeline build
else
  DATA_DIR="$ROOT/deploy/data"
  [[ -f "$DATA_DIR/metadata.json" ]] || fail "no data: run 'uv run python -m pipeline download' and 'build'"
  echo "no data/processed/ and no data/raw/: using the committed snapshot deploy/data/"
fi
if [[ "$DATA_DIR" == "$ROOT/data/processed" && -f deploy/data/metadata.json ]] \
  && ! cmp -s "$DATA_DIR/metadata.json" deploy/data/metadata.json; then
  echo "warning: deploy/data/ differs from data/processed/: the Render fallback is out of date ('make snapshot')"
fi

step "Frontend build"
if [[ ! -d frontend/node_modules ]]; then
  (cd frontend && npm ci --no-audit --no-fund)
fi
if [[ ! -f frontend/dist/index.html ]] \
  || [[ -n "$(find frontend/src frontend/public frontend/index.html frontend/package-lock.json \
                frontend/vite.config.ts -newer frontend/dist/index.html -print -quit)" ]]; then
  (cd frontend && npm run build)
else
  echo "frontend/dist/ is up to date"
fi

step "Backend on :$PORT (log: data/interim/demo_uvicorn.log)"
mkdir -p "$(dirname "$LOG")"
GREEN_PLANNER_DATA_DIR="$DATA_DIR" uv run --frozen uvicorn backend.main:app \
  --host 127.0.0.1 --port "$PORT" >"$LOG" 2>&1 &
UVICORN_PID=$!
trap 'kill "$UVICORN_PID" 2>/dev/null || true; wait "$UVICORN_PID" 2>/dev/null || true' EXIT
for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null && break
  kill -0 "$UVICORN_PID" 2>/dev/null || { cat "$LOG" >&2; fail "backend did not start"; }
  sleep 0.5
done
curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null || fail "backend not ready after 30 s"
echo "ready: http://localhost:$PORT"

if ((LOCAL == 1)); then
  step "Local demo running at http://localhost:$PORT (Ctrl+C to stop)"
  wait "$UVICORN_PID"
else
  step "ngrok: $NGROK_URL (Ctrl+C to stop both)"
  if [[ -t 1 ]]; then
    ngrok http "$PORT" --url "$NGROK_URL"
  else  # no terminal for ngrok's dashboard (e.g. run from a script): plain log lines
    ngrok http "$PORT" --url "$NGROK_URL" --log stdout
  fi
fi
