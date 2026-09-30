#!/usr/bin/env bash
# Demo launcher (plan §8, item 4.1): data → frontend build → uvicorn on :8080 → ngrok.
#
#   scripts/demo.sh                    full demo, public URL via ngrok
#   scripts/demo.sh --local            same app on http://localhost:8080, no ngrok
#   scripts/demo.sh --https [--local]  the backend serves HTTPS with tls/ (scripts/make_cert.sh,
#                                      regenerated when the LAN address changes); ngrok then
#                                      connects to it over HTTPS (Q55)
#
# Environment: DEMO_PORT (8080), DEMO_NGROK_URL, DEMO_HOST (127.0.0.1; 0.0.0.0 to serve other
# devices on a private network directly, preferably with --https).
#
# Data: data/processed/ if built; otherwise it is rebuilt offline from data/raw/;
# otherwise the committed snapshot in deploy/data/ is used (see deploy/README.md).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PATH="$HOME/.local/bin:$PATH"

PORT="${DEMO_PORT:-8080}"
HOST="${DEMO_HOST:-127.0.0.1}"
NGROK_URL="${DEMO_NGROK_URL:-https://green-planner.ngrok.io}"
LOG="$ROOT/data/interim/demo_uvicorn.log"
LOCAL=0
HTTPS=0
for arg in "$@"; do
  case "$arg" in
    --local) LOCAL=1 ;;
    --https) HTTPS=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

step() { printf '\n\033[1;32m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

command -v uv >/dev/null || fail "uv not found (expected in ~/.local/bin)"
command -v npm >/dev/null || fail "npm not found"
if ((LOCAL == 0)); then command -v ngrok >/dev/null || fail "ngrok not found (or use --local)"; fi
if (echo >"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
  fail "port $PORT is already in use (another demo running?)"
fi

SCHEME=http
TLS_ARGS=()
CURL_TLS=()
if ((HTTPS == 1)); then
  # New certificate and key when missing, expiring, or not valid for the current LAN address
  scripts/make_cert.sh --if-needed || fail "could not create the TLS certificate"
  SCHEME=https
  TLS_ARGS=(--ssl-certfile tls/cert.pem --ssl-keyfile tls/key.pem)
  CURL_TLS=(--cacert tls/cert.pem)  # verify against our own certificate, never -k
fi
HEALTH="$SCHEME://127.0.0.1:$PORT/api/health"

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
  echo "warning: deploy/data/ differs from data/processed/: the committed snapshot is out of date ('make snapshot')"
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

step "Backend on $SCHEME://$HOST:$PORT (log: data/interim/demo_uvicorn.log)"
mkdir -p "$(dirname "$LOG")"
ENV_ARGS=()
[[ -f .env ]] && ENV_ARGS=(--env-file .env)  # chat secrets (Q53, Q54); see .env.example
if [[ -n "${GREEN_PLANNER_ADMIN_SECRET:-}" ]] \
  || { [[ -f .env ]] && grep -q '^GREEN_PLANNER_ADMIN_SECRET=.' .env; }; then
  echo "chat access: configured"
else
  echo "chat access: off (no GREEN_PLANNER_ADMIN_SECRET in the environment or .env)"
fi
GREEN_PLANNER_DATA_DIR="$DATA_DIR" uv run --frozen uvicorn backend.main:app \
  --host "$HOST" --port "$PORT" "${TLS_ARGS[@]}" "${ENV_ARGS[@]}" >"$LOG" 2>&1 &
UVICORN_PID=$!
URL_FILE="$ROOT/data/interim/demo_url"  # read by the admin CLI (./chat), so it needs no --url
trap 'kill "$UVICORN_PID" 2>/dev/null || true; wait "$UVICORN_PID" 2>/dev/null || true; rm -f "$URL_FILE"' EXIT
for _ in $(seq 1 60); do
  curl -sf "${CURL_TLS[@]}" "$HEALTH" >/dev/null && break
  kill -0 "$UVICORN_PID" 2>/dev/null || { cat "$LOG" >&2; fail "backend did not start"; }
  sleep 0.5
done
curl -sf "${CURL_TLS[@]}" "$HEALTH" >/dev/null || fail "backend not ready after 30 s"
echo "ready: $SCHEME://localhost:$PORT"
echo "$SCHEME://127.0.0.1:$PORT" >"$URL_FILE"
if [[ "$HOST" != 127.0.0.1 ]]; then
  echo "also on this network: $SCHEME://$(hostname -I | awk '{print $1}'):$PORT"
fi

if ((LOCAL == 1)); then
  step "Local demo running at $SCHEME://localhost:$PORT (Ctrl+C to stop)"
  wait "$UVICORN_PID"
else
  step "ngrok: $NGROK_URL → $SCHEME://127.0.0.1:$PORT (Ctrl+C to stop both)"
  UPSTREAM="$SCHEME://127.0.0.1:$PORT"
  if [[ -t 1 ]]; then
    ngrok http "$UPSTREAM" --url "$NGROK_URL"
  else  # no terminal for ngrok's dashboard (e.g. run from a script): plain log lines
    ngrok http "$UPSTREAM" --url "$NGROK_URL" --log stdout
  fi
fi
