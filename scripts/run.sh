#!/usr/bin/env sh
set -eu
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

MODE=${1:-dev}

read_env() {
  # Read a value from backend/.env without sourcing it (keeps quoting/edge cases out).
  key=$1
  [ -f backend/.env ] || return 0
  sed -n "s/^${key}=//p" backend/.env | tail -n 1
}

HOST=${HOST:-$(read_env HOST)}
PORT=${PORT:-$(read_env PORT)}
HOST=${HOST:-127.0.0.1}
PORT=${PORT:-8787}

cd backend
if [ -x ./.venv/bin/python ]; then
  PYTHON=./.venv/bin/python
elif [ -x ../.venv/bin/python ]; then
  PYTHON=../.venv/bin/python
else
  echo "Keine venv gefunden - zuerst ./scripts/install.sh ausfuehren." >&2
  exit 1
fi

if [ "$MODE" = "prod" ]; then
  [ -f "$ROOT_DIR/frontend/dist/index.html" ] || {
    echo "frontend/dist fehlt - zuerst 'cd frontend && npm run build' ausfuehren." >&2
    exit 1
  }
  exec "$PYTHON" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
fi

exec "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --reload &
API_PID=$!
cd "$ROOT_DIR/frontend"
npm run dev &
WEB_PID=$!
trap 'kill $API_PID $WEB_PID 2>/dev/null || true' EXIT INT TERM
wait
